"""
Failure classification, clustering and alerting (PLAN.md §5.4, shared with Phase 6).

Design (same principle as reports/analyst.py):
  - Classification, clustering and the transient/systemic verdict are all
    deterministic Python over real rows in `task_failures`. The AI never
    decides anything and never produces a number; it only narrates a fact
    pack that code already verified, and only for SYSTEMIC clusters (saves
    Gemini/Groq quota; transient clusters use a fixed template).
  - Phase 6's autonomous engine (core/autonomy.py) consumes find_clusters()
    directly: each cluster dict carries category, chain, wallets, projects,
    per-wallet / per-task counts and the transient/systemic verdict.

Cluster = >= CLUSTER_MIN_EVENTS events of the same category on the same chain
within CLUSTER_WINDOW_MINUTES. The same cluster alerts at most once per
ALERT_COOLDOWN, unless its event count has doubled since the last alert.
Alert dedup state is in memory (lost on restart, like the wizard/confirmation
state) — worst case is one repeated alert after a restart.

Phase 6 changes: new category `gas_underpriced` (tx rejected because the gas
price was too low — the signal that lets the AI raise a wallet's gas
multiplier), and clusters now include `wallet_counts` and `task_stats`.
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models import TaskFailure, AIValidation, Chain, Project
from backend.ai.gemini_client import ask_gemini
from backend.ai.groq_client import ask_groq
from backend.ai.date_injector import get_date_prefix

logger = logging.getLogger("airdrop.failure_analysis")

CLUSTER_WINDOW_MINUTES = 60
CLUSTER_MIN_EVENTS = 3
ALERT_COOLDOWN = timedelta(hours=2)
SKIP_RECORD_THROTTLE_SECS = 30 * 60   # same wallet+chain+category skip recorded at most every 30 min
RETENTION_DAYS = 30

# Categories that resolve on their own; everything else is treated as systemic
# (needs a human), with low_gas decided per cluster (see _assess).
TRANSIENT_CATEGORIES = {"gas_spike", "contract_paused", "memory_pressure", "task_timeout"}

_LABELS = {
    "gas_spike": "gas price spike",
    "contract_paused": "contract paused",
    "memory_pressure": "server memory pressure",
    "task_timeout": "task timeout",
    "low_gas": "insufficient gas token",
    "gas_underpriced": "gas price too low (underpriced)",
    "rpc_error": "RPC / network error",
    "nonce_error": "nonce problem",
    "simulation_revert": "simulation reverted",
    "onchain_revert": "reverted on-chain",
    "approval_failed": "token approval failed",
    "config_error": "task configuration error",
    "unknown": "unclassified error",
}

# Fixed, factual explanations used when AI narration is not needed/available.
_HINTS = {
    "gas_spike": "Tasks were deferred because gas is far above its 6h average. This normally clears by itself.",
    "contract_paused": "The target contract reports paused(). Tasks resume when the project unpauses it.",
    "memory_pressure": "Dispatch was paused because server RAM crossed the alert threshold.",
    "task_timeout": "Tasks exceeded the 8 minute limit. Usually a slow RPC or a congested chain.",
    "low_gas": "Wallets do not hold enough gas token. If many wallets are affected, check that the faucet and the gas wallet are working.",
    "gas_underpriced": "Transactions were rejected because the gas price was too low for current network conditions. Raising the affected wallets' gas multiplier normally fixes this (the AI autonomy engine may do it within its 0.7x-1.8x bounds).",
    "rpc_error": "RPC calls are failing. Check the chain's RPC URLs (/chain_status).",
    "nonce_error": "Nonce locks could not be acquired or the nonce was rejected. Check for stuck transactions (/tx_stuck).",
    "simulation_revert": "Pre-broadcast simulation reverted, so nothing was sent. The task parameters or contract are likely wrong.",
    "onchain_revert": "Transactions were mined but reverted. Gas was spent; check the task parameters.",
    "approval_failed": "ERC20 approval did not succeed, so the main transaction was not sent.",
    "config_error": "A task is missing required configuration (contract, token or registry entry).",
    "unknown": "The failures did not match a known category; see the raw reasons below.",
}


# ── classification ───────────────────────────────────────────────────────────
def classify_error_text(text: str) -> str:
    t = (text or "").lower()
    if "gas_spike" in t or "gas spike" in t:
        return "gas_spike"
    if "contract_paused" in t or "contract is paused" in t:
        return "contract_paused"
    if "memory" in t and "critical" in t:
        return "memory_pressure"
    if "nonce" in t:
        return "nonce_error"
    if any(k in t for k in ("underpriced", "fee too low", "gas price too low",
                            "max fee per gas less than")):
        return "gas_underpriced"
    if "low_gas" in t or "insufficient funds" in t or "insufficient gas" in t or "gas required exceeds" in t:
        return "low_gas"
    if "approval" in t or "allowance" in t:
        return "approval_failed"
    if any(k in t for k in ("all rpc endpoints failed", "connection", "connecterror",
                            "429", "rate limit", "timed out", "timeout", "502", "503", "bad gateway")):
        return "rpc_error"
    if "simulation" in t:
        return "simulation_revert"
    if "revert" in t:
        return "onchain_revert"
    if any(k in t for k in ("missing ", "not registered", "cannot resolve", "not in registry", "no handler")):
        return "config_error"
    return "unknown"


def classify_result(result: dict) -> tuple:
    """result is the dict returned by BaseTask.execute(). Returns (category, reason)."""
    reason = str((result or {}).get("reason") or "")
    if reason == "simulation_failed":
        err = ((result.get("details") or {}).get("error")) or ""
        return "simulation_revert", f"simulation failed: {err}"[:300]
    if reason == "tx_failed_onchain":
        return "onchain_revert", "transaction reverted on-chain"
    return classify_error_text(reason), (reason or "no reason given")[:300]


# ── recording ────────────────────────────────────────────────────────────────
_last_skip_recorded: Dict[tuple, float] = {}


async def record_failure(
    *, wallet_id: Optional[int], chain_id: Optional[int], project_id: Optional[int],
    task_config_id: Optional[int], task_type: str, outcome: str, category: str, reason: str,
) -> None:
    """outcome: 'failed' (counts toward wallet/circuit breaker) or 'skipped'.
    Never raises — recording must not be able to break task execution."""
    try:
        if outcome == "skipped":
            key = (wallet_id, chain_id, category)
            now = time.monotonic()
            last = _last_skip_recorded.get(key)
            if last is not None and now - last < SKIP_RECORD_THROTTLE_SECS:
                return
            _last_skip_recorded[key] = now
        async with async_session() as db:
            db.add(TaskFailure(
                wallet_id=wallet_id, chain_id=chain_id, project_id=project_id,
                task_config_id=task_config_id, task_type=task_type, outcome=outcome,
                category=category, reason=(reason or "")[:500],
            ))
            await db.commit()
    except Exception as e:
        logger.error("record_failure error: %s", e)


# ── clustering ───────────────────────────────────────────────────────────────
def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _assess(c: dict) -> None:
    cat = c["category"]
    if cat in TRANSIENT_CATEGORIES:
        systemic = False
    elif cat == "low_gas":
        systemic = c["distinct_wallets"] >= 3
    else:
        systemic = True
    c["classification"] = "systemic" if systemic else "transient"
    if not systemic:
        c["severity"] = "info"
    elif c["count"] >= 10 or c["distinct_wallets"] >= 5:
        c["severity"] = "critical"
    else:
        c["severity"] = "warning"


async def find_clusters(
    db: AsyncSession,
    window_minutes: int = CLUSTER_WINDOW_MINUTES,
    min_events: int = CLUSTER_MIN_EVENTS,
) -> List[dict]:
    since = _utcnow_naive() - timedelta(minutes=window_minutes)
    rows = (await db.execute(select(TaskFailure).where(TaskFailure.created_at >= since))).scalars().all()

    groups: Dict[tuple, List[TaskFailure]] = {}
    for r in rows:
        groups.setdefault((r.category, r.chain_id), []).append(r)

    clusters = []
    for (category, chain_id), items in groups.items():
        if len(items) < min_events:
            continue
        reasons: Dict[str, int] = {}
        wallet_counts: Dict[int, int] = {}
        task_raw: Dict[int, dict] = {}
        for r in items:
            key = (r.reason or "")[:80]
            reasons[key] = reasons.get(key, 0) + 1
            if r.wallet_id is not None:
                wallet_counts[r.wallet_id] = wallet_counts.get(r.wallet_id, 0) + 1
            if r.task_config_id is not None:
                t = task_raw.setdefault(r.task_config_id, {"count": 0, "wallets": set()})
                t["count"] += 1
                if r.wallet_id is not None:
                    t["wallets"].add(r.wallet_id)
        c = {
            "category": category,
            "chain_id": chain_id,
            "count": len(items),
            "failed_count": sum(1 for r in items if r.outcome == "failed"),
            "skipped_count": sum(1 for r in items if r.outcome == "skipped"),
            "wallet_ids": sorted({r.wallet_id for r in items if r.wallet_id is not None}),
            "project_ids": sorted({r.project_id for r in items if r.project_id is not None}),
            "top_reasons": sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:3],
            "window_minutes": window_minutes,
            # Phase 6: per-target evidence for the autonomy engine
            "wallet_counts": wallet_counts,
            "task_stats": {
                tid: {"count": t["count"], "distinct_wallets": len(t["wallets"])}
                for tid, t in task_raw.items()
            },
        }
        c["distinct_wallets"] = len(c["wallet_ids"])
        _assess(c)
        clusters.append(c)
    return clusters


# ── alert dedup ──────────────────────────────────────────────────────────────
_alert_state: Dict[tuple, dict] = {}


def _should_alert(c: dict) -> bool:
    prior = _alert_state.get((c["category"], c["chain_id"]))
    if not prior:
        return True
    if _utcnow_naive() - prior["at"] >= ALERT_COOLDOWN:
        return True
    return c["count"] >= prior["count"] * 2   # escalation


def _mark_alerted(c: dict) -> None:
    _alert_state[(c["category"], c["chain_id"])] = {"at": _utcnow_naive(), "count": c["count"]}


# ── message rendering ────────────────────────────────────────────────────────
def _md_safe(s: str) -> str:
    """create_and_send_alert uses Telegram legacy Markdown; stray _ * ` [ break parsing."""
    return (s or "").replace("_", " ").replace("*", "").replace("`", "").replace("[", "(").replace("]", ")")


_SYSTEM_PROMPT = (
    "You are writing a short alert for the operator of an automated TESTNET airdrop-farming agent. "
    "You receive a JSON fact pack computed by code; every number and classification in it is verified. "
    "In 2-3 plain sentences, explain the most likely cause of this failure cluster using ONLY the category "
    "and reasons given, and say what the operator should check first. "
    "Rules: never invent numbers, names, addresses or causes not supported by the fact pack; use the word 'likely'; "
    "do not recommend changing configuration values; no markdown, no lists."
)


async def _narrate(db: AsyncSession, facts: dict) -> Optional[str]:
    prompt = f"{get_date_prefix()}\n\nFACT PACK:\n{json.dumps(facts, indent=2)}\n\nWrite the alert text now."
    gemini_text = groq_text = None
    try:
        gemini_text = await ask_gemini(_SYSTEM_PROMPT, prompt, temperature=0.3)
    except Exception as e:
        logger.warning("failure narration: Gemini failed (%s), trying Groq", e)
        try:
            groq_text = await ask_groq(_SYSTEM_PROMPT, prompt, temperature=0.3)
        except Exception as e2:
            logger.warning("failure narration: Groq failed too (%s)", e2)
    narrative = (gemini_text or groq_text or "").strip() or None
    try:  # log like analyst.py does — availability signal, nothing to approve
        db.add(AIValidation(
            task_type="failure_analysis", input_hash="n/a",
            groq_output={"text": groq_text} if groq_text else {},
            gemini_output={"text": gemini_text} if gemini_text else {},
            agreement_score=100 if gemini_text else (50 if groq_text else 0),
            conflict_fields=[], final_decision={"narrative": narrative} if narrative else {},
            requires_human=False, resolved=True,
        ))
        await db.commit()
    except Exception as e:
        logger.error("failure_analysis AIValidation log failed: %s", e)
    return narrative


async def _render(db: AsyncSession, c: dict) -> str:
    chain = await db.get(Chain, c["chain_id"]) if c["chain_id"] else None
    chain_name = chain.name if chain else "unknown chain"
    proj_names = []
    for pid in c["project_ids"][:5]:
        p = await db.get(Project, pid)
        if p:
            proj_names.append(p.name)

    label = _LABELS.get(c["category"], c["category"])
    wallets = ", ".join(f"#{w}" for w in c["wallet_ids"][:8]) or "n/a"
    if len(c["wallet_ids"]) > 8:
        wallets += f" +{len(c['wallet_ids']) - 8} more"

    body = _HINTS.get(c["category"], _HINTS["unknown"])
    if c["classification"] == "systemic":
        facts = {
            "category": c["category"], "category_label": label, "chain": chain_name,
            "events": c["count"], "failed": c["failed_count"], "skipped": c["skipped_count"],
            "distinct_wallets": c["distinct_wallets"], "projects": proj_names,
            "window_minutes": c["window_minutes"],
            "top_reasons": [{"reason": r, "count": n} for r, n in c["top_reasons"]],
        }
        narrative = await _narrate(db, facts)
        if narrative:
            body = narrative

    lines = [
        f"{c['count']} events on {_md_safe(chain_name)}: {label} "
        f"({c['failed_count']} failed, {c['skipped_count']} skipped, last {c['window_minutes']} min)",
        f"Assessment: {c['classification']}",
        f"Wallets: {wallets}",
    ]
    if proj_names:
        lines.append("Projects: " + _md_safe(", ".join(proj_names)))
    lines += ["", _md_safe(body)]
    if c["top_reasons"]:
        lines += ["", "Top reasons:"] + [f"- {n}x {_md_safe(r)}" for r, n in c["top_reasons"]]
    return "\n".join(lines)


# ── entry point (scheduler, every 10 min) ────────────────────────────────────
async def analyze_and_alert() -> List[dict]:
    from backend.core.kill_switch import is_emergency_stop
    from backend.telegram.alerts import create_and_send_alert

    if is_emergency_stop():
        return []

    pending = []
    async with async_session() as db:
        for c in await find_clusters(db):
            if not _should_alert(c):
                continue
            pending.append((c, await _render(db, c)))

    sent = []
    for c, message in pending:
        try:
            await create_and_send_alert(
                type="failure_cluster", severity=c["severity"], message=message,
                chain_id=c["chain_id"],
                project_id=c["project_ids"][0] if len(c["project_ids"]) == 1 else None,
            )
            _mark_alerted(c)
            sent.append(c)
        except Exception as e:
            logger.error("failure cluster alert failed: %s", e)
    return sent


async def purge_old_failures(days: int = RETENTION_DAYS) -> int:
    cutoff = _utcnow_naive() - timedelta(days=days)
    async with async_session() as db:
        res = await db.execute(delete(TaskFailure).where(TaskFailure.created_at < cutoff))
        await db.commit()
        return res.rowcount or 0
