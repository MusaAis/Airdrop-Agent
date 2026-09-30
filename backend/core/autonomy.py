"""
AI-managed tasks and wallets (PLAN.md §5.3, Phase 6).

One cycle runs every 10 minutes (scheduler._run_ai_autonomy):

  1. CODE proposes changes from verified failure data (failure_analysis
     .find_clusters + task_failures). Every new value is computed by code
     inside hard bounds — the AI never invents a value or a target.
  2. The dual-AI reviewer (Gemini + Groq, dual_ai_validate task_type="autonomy")
     acts as a veto gate on each proposal. Only the single field `approved` is
     compared for agreement (prose is never compared, same principle as
     orchestrator.py).
       agreement >= 70% and approved  -> applied autonomously
       agreement >= 70% and rejected  -> vetoed (logged, nothing changes)
       agreement <  70% / Groq down   -> saved as a SUGGESTION, notify and wait
  3. Every applied action is logged in ai_actions (before/after/why), sent to
     Telegram, and can be undone with `/ai_reject A<id>` or from the dashboard.

Allowed actions (this is the complete list — see ACTION_TYPES):
  wallet_pause      pause an active wallet that is about to hit the hard cooldown
                    because of a systemic cause; auto-resumes when the cause clears
  gas_multiplier    raise WalletSettings.gas_multiplier by 0.1, ceiling 1.8
  task_disable      disable an existing task config that keeps failing for
                    task-level reasons across wallets
  project_priority  lower a persistently failing project's priority by 1 (min 1)

NEVER autonomous (no code path exists for these): adding projects or task
configs, private key / seed handling, claim execution, deleting anything.

Guardrails: 10 adjustments per target per 24h, max 5 AI reviews per cycle,
per-action-type cooldowns, a 12h cooldown after a human undo, the freeze flag
(persisted, survives restarts), and no activity during emergency stop.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models import Wallet, WalletSettings, Project, TaskConfig, TaskFailure, Chain
from backend.core.autonomy_models import AIAction, AutonomyState
from backend.core.failure_analysis import find_clusters, _md_safe, _utcnow_naive
from backend.core.kill_switch import (
    is_emergency_stop, is_ai_autonomy_paused, set_ai_autonomy_paused,
)
from backend.ai.orchestrator import dual_ai_validate
from backend.ai.date_injector import get_date_prefix

logger = logging.getLogger("airdrop.autonomy")

# ── the complete list of things the AI may ever do ───────────────────────────
ACTION_TYPES = ("wallet_pause", "gas_multiplier", "task_disable", "project_priority")

# ── limits (PLAN.md §7) ──────────────────────────────────────────────────────
MAX_ADJUSTMENTS_PER_TARGET_PER_DAY = 10   # §7.1
GAS_MULT_MIN = 0.7                        # §7.2
GAS_MULT_MAX = 1.8
GAS_MULT_STEP = 0.1
PRIORITY_MIN = 1
MAX_EVALUATIONS_PER_CYCLE = 5             # caps AI quota use and cascades
SUGGESTION_TTL = timedelta(hours=24)
HUMAN_UNDO_COOLDOWN = timedelta(hours=12)
MIN_PAUSE_MINUTES = 30

# ── triggers ─────────────────────────────────────────────────────────────────
PAUSE_CAUSES = {"low_gas", "rpc_error", "nonce_error"}
PAUSE_AFTER_FAILURES = 2                  # hard cooldown is at 3 (worker_pool)
GAS_UNDERPRICED_MIN_EVENTS = 2            # per wallet, inside one cluster
TASK_BREAK_CATEGORIES = {"config_error", "simulation_revert", "approval_failed", "onchain_revert"}
TASK_DISABLE_MIN_EVENTS = 3
PROJECT_FAULT_CATEGORIES = {"config_error", "simulation_revert", "onchain_revert", "approval_failed", "unknown"}
PROJECT_FAIL_24H = 10

COOLDOWN = {
    "wallet_pause": timedelta(hours=2),
    "gas_multiplier": timedelta(hours=3),      # must exceed the 60 min cluster window
    "task_disable": timedelta(hours=6),
    "project_priority": timedelta(hours=24),
}


@dataclass
class Proposal:
    action_type: str
    target_type: str
    target_id: int
    summary: str
    reason: str
    after: Dict[str, Any]
    chain_id: Optional[int] = None
    project_id: Optional[int] = None
    cause_category: Optional[str] = None
    facts: Dict[str, Any] = field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════════════════
# freeze flag persistence
# ═════════════════════════════════════════════════════════════════════════════
async def load_autonomy_state() -> None:
    """Call at startup: restores the persisted freeze flag into kill_switch."""
    try:
        async with async_session() as db:
            st = await db.get(AutonomyState, 1)
            set_ai_autonomy_paused(bool(st and st.paused))
            if st and st.paused:
                logger.warning("AI autonomy is FROZEN (restored from DB)")
    except Exception as e:
        logger.error("load_autonomy_state failed: %s", e)


async def set_autonomy_paused(db: AsyncSession, paused: bool, by: str) -> None:
    """Single write path for the freeze flag (Telegram + dashboard share it)."""
    st = await db.get(AutonomyState, 1)
    if st is None:
        db.add(AutonomyState(id=1, paused=paused, updated_by=by))
    else:
        st.paused = paused
        st.updated_by = by
        st.updated_at = _utcnow_naive()
    await db.commit()
    set_ai_autonomy_paused(paused)


# ═════════════════════════════════════════════════════════════════════════════
# proposals (deterministic — the AI never picks targets or values)
# ═════════════════════════════════════════════════════════════════════════════
async def _wallet_pause_proposals(db: AsyncSession, clusters: List[dict]) -> List[Proposal]:
    out = []
    for c in clusters:
        if c["category"] not in PAUSE_CAUSES or c["classification"] != "systemic":
            continue
        for wid, n in c["wallet_counts"].items():
            if n < 2:
                continue
            w = await db.get(Wallet, wid)
            if not w or w.status != "active" or w.is_gas_wallet:
                continue
            if (w.failure_count or 0) < PAUSE_AFTER_FAILURES:
                continue
            out.append(Proposal(
                action_type="wallet_pause", target_type="wallet", target_id=wid,
                summary=f"Pause wallet #{wid} ({w.address[:8]}...)",
                reason=(
                    f"{n} '{c['category']}' events for this wallet in the last {c['window_minutes']} min "
                    f"(cluster: {c['count']} events across {c['distinct_wallets']} wallet(s)). "
                    f"The wallet has {w.failure_count} consecutive failures and would hit the hard "
                    f"cooldown at 3; the cause looks systemic, not wallet-specific."
                ),
                after={"status": "paused"}, chain_id=c["chain_id"], cause_category=c["category"],
                facts={"category": c["category"], "wallet_events": n, "cluster_events": c["count"],
                       "cluster_wallets": c["distinct_wallets"], "wallet_failure_count": w.failure_count},
            ))
    return out


async def _gas_multiplier_proposals(db: AsyncSession, clusters: List[dict]) -> List[Proposal]:
    out = []
    for c in clusters:
        if c["category"] != "gas_underpriced":
            continue
        for wid, n in c["wallet_counts"].items():
            if n < GAS_UNDERPRICED_MIN_EVENTS:
                continue
            w = await db.get(Wallet, wid)
            if not w or w.status != "active":
                continue
            ws = (await db.execute(
                select(WalletSettings).where(WalletSettings.wallet_id == wid)
            )).scalar_one_or_none()
            current = float(ws.gas_multiplier) if ws and ws.gas_multiplier is not None else 1.0
            new = round(min(GAS_MULT_MAX, current + GAS_MULT_STEP), 2)
            if new <= current + 1e-9:
                continue  # already at the ceiling
            out.append(Proposal(
                action_type="gas_multiplier", target_type="wallet", target_id=wid,
                summary=f"Raise gas multiplier for wallet #{wid}: {current:.2f} -> {new:.2f}",
                reason=(
                    f"{n} transactions from this wallet were rejected as underpriced in the last "
                    f"{c['window_minutes']} min (cluster: {c['count']} events). "
                    f"Allowed range {GAS_MULT_MIN}-{GAS_MULT_MAX}, max step {GAS_MULT_STEP}."
                ),
                after={"gas_multiplier": new}, chain_id=c["chain_id"],
                facts={"current_multiplier": current, "wallet_events": n, "cluster_events": c["count"]},
            ))
    return out


async def _task_disable_proposals(db: AsyncSession, clusters: List[dict]) -> List[Proposal]:
    out = []
    for c in clusters:
        if c["category"] not in TASK_BREAK_CATEGORIES:
            continue
        for tid, st in c["task_stats"].items():
            if st["count"] < TASK_DISABLE_MIN_EVENTS:
                continue
            # config errors are wallet-independent; the others must span 2+ wallets
            # so a single bad wallet cannot get a healthy task disabled
            if c["category"] != "config_error" and st["distinct_wallets"] < 2:
                continue
            tc = await db.get(TaskConfig, tid)
            if not tc or not tc.enabled:
                continue
            project = await db.get(Project, tc.project_id)
            if not project:
                continue
            out.append(Proposal(
                action_type="task_disable", target_type="task", target_id=tid,
                summary=f"Disable task #{tid} ({tc.task_type}) of project '{project.name}'",
                reason=(
                    f"{st['count']} '{c['category']}' events from this task across "
                    f"{st['distinct_wallets']} wallet(s) in the last {c['window_minutes']} min."
                ),
                after={"enabled": False}, chain_id=c["chain_id"], project_id=tc.project_id,
                facts={"category": c["category"], "task_type": tc.task_type, "project": project.name,
                       "events": st["count"], "distinct_wallets": st["distinct_wallets"]},
            ))
    return out


async def _project_priority_proposals(db: AsyncSession) -> List[Proposal]:
    since = _utcnow_naive() - timedelta(hours=24)
    rows = (await db.execute(
        select(
            TaskFailure.project_id,
            func.count(TaskFailure.id),
            func.count(func.distinct(TaskFailure.wallet_id)),
        )
        .where(
            TaskFailure.outcome == "failed",
            TaskFailure.created_at >= since,
            TaskFailure.project_id.is_not(None),
            TaskFailure.category.in_(PROJECT_FAULT_CATEGORIES),
        )
        .group_by(TaskFailure.project_id)
        .having(func.count(TaskFailure.id) >= PROJECT_FAIL_24H)
    )).all()

    out = []
    for pid, n, wallets in rows:
        if wallets < 2:
            continue
        p = await db.get(Project, pid)
        if not p or p.status != "active":
            continue
        cur = int(p.priority or 5)
        if cur <= PRIORITY_MIN:
            continue
        out.append(Proposal(
            action_type="project_priority", target_type="project", target_id=pid,
            summary=f"Lower priority of project '{p.name}': {cur} -> {cur - 1}",
            reason=(
                f"{n} project-level failures across {wallets} wallets in the last 24h "
                f"(config/simulation/revert/approval categories only — infrastructure "
                f"problems such as RPC or gas are excluded)."
            ),
            after={"priority": cur - 1}, project_id=pid,
            facts={"failures_24h": n, "distinct_wallets": wallets, "current_priority": cur},
        ))
    return out


async def _gather_proposals(db: AsyncSession) -> List[Proposal]:
    clusters = await find_clusters(db)
    proposals: List[Proposal] = []
    proposals += await _wallet_pause_proposals(db, clusters)
    proposals += await _gas_multiplier_proposals(db, clusters)
    proposals += await _task_disable_proposals(db, clusters)
    proposals += await _project_priority_proposals(db)
    return proposals


# ═════════════════════════════════════════════════════════════════════════════
# guardrails
# ═════════════════════════════════════════════════════════════════════════════
async def _blocked_by_history(db: AsyncSession, p: Proposal) -> bool:
    """Cooldown, an open suggestion, or a recent human undo for the same target."""
    now = _utcnow_naive()
    since = now - COOLDOWN[p.action_type]
    same = (
        AIAction.action_type == p.action_type,
        AIAction.target_type == p.target_type,
        AIAction.target_id == p.target_id,
    )
    recent = await db.execute(
        select(AIAction.id).where(
            *same,
            or_(
                AIAction.created_at >= since,
                AIAction.reverted_at >= since,
                AIAction.status == "suggested",
            ),
        ).limit(1)
    )
    if recent.first():
        return True
    undone = await db.execute(
        select(AIAction.id).where(
            *same,
            AIAction.reverted_by == "human",
            AIAction.reverted_at >= now - HUMAN_UNDO_COOLDOWN,
        ).limit(1)
    )
    return undone.first() is not None


async def _rate_limited(db: AsyncSession, p: Proposal) -> bool:
    since = _utcnow_naive() - timedelta(hours=24)
    n = (await db.execute(
        select(func.count()).select_from(AIAction).where(
            AIAction.target_type == p.target_type,
            AIAction.target_id == p.target_id,
            AIAction.decided_by == "ai",
            AIAction.status.in_(("applied", "reverted")),
            AIAction.created_at >= since,
        )
    )).scalar() or 0
    return n >= MAX_ADJUSTMENTS_PER_TARGET_PER_DAY


async def _expire_stale_suggestions(db: AsyncSession) -> None:
    cutoff = _utcnow_naive() - SUGGESTION_TTL
    rows = (await db.execute(
        select(AIAction).where(AIAction.status == "suggested", AIAction.created_at < cutoff)
    )).scalars().all()
    for r in rows:
        r.status = "expired"
    if rows:
        await db.commit()


# ═════════════════════════════════════════════════════════════════════════════
# the change itself (bounds are enforced HERE, independent of who asked)
# ═════════════════════════════════════════════════════════════════════════════
async def _do_change(db: AsyncSession, action_type: str, target_id: int, after: dict) -> Tuple[dict, dict]:
    """Mutates the target (no commit). Returns (before, after) from LIVE state."""
    if action_type not in ACTION_TYPES:
        raise ValueError(f"'{action_type}' is not an allowed autonomous action")
    now = _utcnow_naive()

    if action_type == "wallet_pause":
        w = await db.get(Wallet, target_id)
        if not w:
            raise ValueError("wallet not found")
        if w.is_gas_wallet:
            raise ValueError("gas wallets are never paused autonomously")
        if w.status != "active":
            raise ValueError(f"wallet is '{w.status}', not active")
        before = {"status": w.status, "failure_count": w.failure_count}
        w.status = "paused"
        return before, {"status": "paused"}

    if action_type == "gas_multiplier":
        ws = (await db.execute(
            select(WalletSettings).where(WalletSettings.wallet_id == target_id)
        )).scalar_one_or_none()
        if ws is None:
            ws = WalletSettings(wallet_id=target_id)
            db.add(ws)
            await db.flush()
        current = float(ws.gas_multiplier) if ws.gas_multiplier is not None else 1.0
        new = round(float(after["gas_multiplier"]), 2)
        if new < GAS_MULT_MIN - 1e-9 or new > GAS_MULT_MAX + 1e-9:
            raise ValueError(f"gas multiplier {new} outside allowed range {GAS_MULT_MIN}-{GAS_MULT_MAX}")
        if abs(new - current) > GAS_MULT_STEP + 1e-6:
            raise ValueError(f"change {current} -> {new} exceeds the {GAS_MULT_STEP} step limit (state changed?)")
        ws.gas_multiplier = new
        ws.updated_at = now
        return {"gas_multiplier": current}, {"gas_multiplier": new}

    if action_type == "task_disable":
        tc = await db.get(TaskConfig, target_id)
        if not tc:
            raise ValueError("task config not found")
        if not tc.enabled:
            raise ValueError("task is already disabled")
        tc.enabled = False
        return {"enabled": True}, {"enabled": False}

    # project_priority
    p = await db.get(Project, target_id)
    if not p:
        raise ValueError("project not found")
    if p.status != "active":
        raise ValueError(f"project is '{p.status}', not active")
    cur = int(p.priority or 5)
    new = int(after["priority"])
    if new < PRIORITY_MIN or new != cur - 1:
        raise ValueError(f"priority must move exactly one step down from {cur} (minimum {PRIORITY_MIN})")
    p.priority = new
    return {"priority": cur}, {"priority": new}


async def _do_revert(db: AsyncSession, row: AIAction) -> None:
    """Undo an applied action. Refuses if someone changed the target since —
    an undo must never overwrite a newer human decision."""
    before = row.before_state or {}
    after = row.after_state or {}
    now = _utcnow_naive()

    if row.action_type == "wallet_pause":
        w = await db.get(Wallet, row.target_id)
        if not w:
            raise ValueError("wallet not found")
        if w.status != "paused":
            raise ValueError(f"wallet is now '{w.status}'; leaving it alone")
        w.status = before.get("status", "active")
        w.failure_count = 0   # the failures were attributed to a systemic cause
    elif row.action_type == "gas_multiplier":
        ws = (await db.execute(
            select(WalletSettings).where(WalletSettings.wallet_id == row.target_id)
        )).scalar_one_or_none()
        if ws is None:
            raise ValueError("wallet settings not found")
        if abs(float(ws.gas_multiplier or 1.0) - float(after["gas_multiplier"])) > 1e-6:
            raise ValueError("gas multiplier was changed since; not overriding it")
        ws.gas_multiplier = float(before["gas_multiplier"])
        ws.updated_at = now
    elif row.action_type == "task_disable":
        tc = await db.get(TaskConfig, row.target_id)
        if not tc:
            raise ValueError("task config not found")
        if tc.enabled:
            raise ValueError("task is already enabled again")
        tc.enabled = bool(before.get("enabled", True))
    elif row.action_type == "project_priority":
        p = await db.get(Project, row.target_id)
        if not p:
            raise ValueError("project not found")
        if int(p.priority or 0) != int(after["priority"]):
            raise ValueError("priority was changed since; not overriding it")
        p.priority = int(before["priority"])
    else:
        raise ValueError(f"'{row.action_type}' is not an allowed autonomous action")


# ═════════════════════════════════════════════════════════════════════════════
# AI review gate
# ═════════════════════════════════════════════════════════════════════════════
_SYSTEM_PROMPT = (
    "You are a safety reviewer for an automated TESTNET airdrop-farming agent. Code has already "
    "computed a small, reversible change from real failure data; you decide whether to let it run "
    "without a human. Approve only if the evidence directly supports this exact change on this exact "
    "target and the change is not merely masking a different problem (for example a misconfiguration). "
    "Reject if the evidence is thin, contradictory, or the cause looks unrelated to the target. "
    "Never propose a different change. Output JSON only, no markdown."
)


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("true", "yes", "approve", "approved")


def _review_prompt(p: Proposal) -> str:
    facts = {
        "action": p.action_type,
        "target": f"{p.target_type} #{p.target_id}",
        "summary": p.summary,
        "evidence": p.reason,
        "proposed_change": p.after,
        "context": p.facts,
        "guarantees": "Reversible, bounded, logged, and the operator is notified immediately.",
    }
    return (
        f"{get_date_prefix()}\n\nPROPOSED AUTONOMOUS ACTION:\n{json.dumps(facts, indent=2, default=str)}\n\n"
        'Output JSON only: {"approved": true or false, "reasoning": "one or two sentences"}'
    )


async def _ai_review(db: AsyncSession, p: Proposal):
    """Returns (validation | None, reasoning). None means the review could not run."""
    try:
        v = await dual_ai_validate(
            task_type="autonomy",
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_review_prompt(p),
            db=db,
        )
    except Exception as e:
        logger.error("autonomy review failed for %s #%s: %s", p.action_type, p.target_id, e)
        try:
            await db.rollback()
        except Exception:
            pass
        return None, "AI review unavailable"
    g = v.gemini_output or {}
    r = v.groq_output or {}
    reasoning = str(g.get("reasoning") or r.get("reasoning") or "")[:400]
    return v, reasoning


# ═════════════════════════════════════════════════════════════════════════════
# notifications
# ═════════════════════════════════════════════════════════════════════════════
async def _notify(row: AIAction, kind: str) -> None:
    """kind: applied | suggested | resumed. Never raises."""
    try:
        from backend.telegram.alerts import create_and_send_alert
        ref = f"A{row.id}"
        if kind == "applied":
            head = f"🤖 Autonomous action {ref}"
            foot = f"Undo: `/ai_reject {ref}`"
            sev = "warning" if row.action_type in ("wallet_pause", "task_disable") else "info"
        elif kind == "suggested":
            head = f"🤔 AI suggestion {ref} needs your approval"
            foot = f"Approve: `/ai_approve {ref}`  Dismiss: `/ai_reject {ref}`"
            sev = "warning"
        else:
            head = f"↩️ Auto-reverted {ref}"
            foot = None
            sev = "info"
        lines = [head, _md_safe(row.summary), "Why: " + _md_safe(row.reason)]
        if row.ai_reasoning and row.agreement_score is not None:
            lines.append(f"AI review ({row.agreement_score}% agreement): {_md_safe(row.ai_reasoning)}")
        if foot:
            lines.append(foot)
        await create_and_send_alert(
            type="ai_action", severity=sev, message="\n".join(lines),
            wallet_id=row.target_id if row.target_type == "wallet" else None,
            project_id=row.project_id, chain_id=row.chain_id,
        )
    except Exception as e:
        logger.error("autonomy notify failed: %s", e)


# ═════════════════════════════════════════════════════════════════════════════
# processing one proposal
# ═════════════════════════════════════════════════════════════════════════════
async def _process_proposal(db: AsyncSession, p: Proposal) -> str:
    """Returns one of: applied | suggested | vetoed | failed."""
    validation, reasoning = await _ai_review(db, p)

    if validation is None or validation.requires_human:
        verdict = "suggest"
    elif not _truthy((validation.final_decision or {}).get("approved")):
        verdict = "veto"
    else:
        verdict = "apply"

    # the freeze can be flipped while the LLM calls were in flight
    if verdict == "apply" and (is_ai_autonomy_paused() or is_emergency_stop()):
        verdict = "suggest"

    base = dict(
        action_type=p.action_type, target_type=p.target_type, target_id=p.target_id,
        chain_id=p.chain_id, project_id=p.project_id, summary=p.summary, reason=p.reason,
        ai_reasoning=reasoning or None, after_state=p.after, cause_category=p.cause_category,
        validation_id=validation.id if validation is not None else None,
        agreement_score=validation.agreement_score if validation is not None else None,
    )

    if verdict == "apply":
        try:
            before, after = await _do_change(db, p.action_type, p.target_id, p.after)
        except Exception as e:
            await db.rollback()
            db.add(AIAction(**base, status="failed", decided_by="ai", error=str(e)[:300]))
            await db.commit()
            logger.warning("autonomy apply failed (%s #%s): %s", p.action_type, p.target_id, e)
            return "failed"
        row = AIAction(**{**base, "after_state": after}, status="applied", decided_by="ai",
                       before_state=before, applied_at=_utcnow_naive())
        db.add(row)
        await db.commit()
        await db.refresh(row)
        logger.info("AI action applied: A%s %s", row.id, row.summary)
        await _notify(row, "applied")
        return "applied"

    if verdict == "veto":
        db.add(AIAction(**base, status="vetoed", decided_by="ai"))
        await db.commit()
        logger.info("AI review vetoed: %s", p.summary)
        return "vetoed"

    row = AIAction(**base, status="suggested")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await _notify(row, "suggested")
    return "suggested"


# ═════════════════════════════════════════════════════════════════════════════
# auto-resume of AI-paused wallets
# ═════════════════════════════════════════════════════════════════════════════
async def _cause_cleared(db: AsyncSession, row: AIAction, wallet: Wallet) -> bool:
    cat = row.cause_category
    now = _utcnow_naive()
    chain = await db.get(Chain, row.chain_id) if row.chain_id else None

    if cat == "low_gas":
        if not chain:
            return True
        try:
            from backend.wallet.balance import get_gas_token_balance
            bal = await get_gas_token_balance(chain, wallet.address)
            return float(bal) >= float(chain.min_gas_balance_warning)
        except Exception:
            return False

    if cat == "rpc_error":
        if not chain:
            return True
        recent = await db.execute(
            select(TaskFailure.id).where(
                TaskFailure.category == "rpc_error",
                TaskFailure.chain_id == chain.id,
                TaskFailure.created_at >= now - timedelta(minutes=30),
            ).limit(1)
        )
        if recent.first():
            return False
        try:
            from backend.chains.rpc_pool import get_web3
            await get_web3(chain)
            return True
        except Exception:
            return False

    # nonce_error and anything else: plain time-based release
    return bool(row.applied_at) and now - row.applied_at >= timedelta(minutes=60)


async def _auto_resume(db: AsyncSession) -> int:
    now = _utcnow_naive()
    rows = (await db.execute(
        select(AIAction).where(
            AIAction.action_type == "wallet_pause",
            AIAction.status == "applied",
            AIAction.decided_by == "ai",
        )
    )).scalars().all()

    resumed = 0
    for row in rows:
        row_id = row.id
        wallet = await db.get(Wallet, row.target_id)
        if not wallet or wallet.status != "paused":
            # someone already resumed/changed it — just close the log entry
            row.status = "reverted"
            row.reverted_at = now
            row.reverted_by = "human"
            await db.commit()
            continue
        if row.applied_at and now - row.applied_at < timedelta(minutes=MIN_PAUSE_MINUTES):
            continue
        if not await _cause_cleared(db, row, wallet):
            continue
        try:
            await _do_revert(db, row)
        except Exception as e:
            await db.rollback()
            logger.warning("auto-resume of A%s failed: %s", row_id, e)
            continue
        row = await db.get(AIAction, row_id)
        row.status = "reverted"
        row.reverted_at = now
        row.reverted_by = "auto"
        await db.commit()
        await _notify(row, "resumed")
        resumed += 1
    return resumed


# ═════════════════════════════════════════════════════════════════════════════
# the cycle (scheduler entry point)
# ═════════════════════════════════════════════════════════════════════════════
async def run_autonomy_cycle() -> dict:
    if is_ai_autonomy_paused() or is_emergency_stop():
        return {"skipped": "frozen" if is_ai_autonomy_paused() else "emergency_stop"}

    stats = {"resumed": 0, "applied": 0, "suggested": 0, "vetoed": 0, "failed": 0, "rate_limited": 0}
    async with async_session() as db:
        await _expire_stale_suggestions(db)
        stats["resumed"] = await _auto_resume(db)

        evaluated = 0
        for p in await _gather_proposals(db):
            if evaluated >= MAX_EVALUATIONS_PER_CYCLE:
                break
            if is_ai_autonomy_paused() or is_emergency_stop():
                break
            if await _blocked_by_history(db, p):
                continue
            if await _rate_limited(db, p):
                stats["rate_limited"] += 1
                continue
            evaluated += 1
            stats[await _process_proposal(db, p)] += 1
    return stats


# ═════════════════════════════════════════════════════════════════════════════
# human-facing operations (Telegram + dashboard)
# ═════════════════════════════════════════════════════════════════════════════
async def approve_action(db: AsyncSession, action_id: int) -> Tuple[bool, str]:
    """Apply a suggestion. Bounds are re-checked against LIVE state."""
    row = await db.get(AIAction, action_id)
    if not row:
        return False, f"Action A{action_id} not found."
    if row.status != "suggested":
        return False, f"A{action_id} is '{row.status}', not awaiting approval."
    try:
        before, after = await _do_change(db, row.action_type, row.target_id, row.after_state or {})
    except Exception as e:
        await db.rollback()
        row = await db.get(AIAction, action_id)
        row.status = "failed"
        row.error = str(e)[:300]
        await db.commit()
        return False, f"Could not apply A{action_id}: {e}"
    row.before_state = before
    row.after_state = after
    row.status = "applied"
    row.decided_by = "human"
    row.applied_at = _utcnow_naive()
    await db.commit()
    return True, f"✅ Applied A{action_id}: {row.summary}"


async def undo_action(db: AsyncSession, action_id: int) -> Tuple[bool, str]:
    """Dismiss a suggestion, or revert an applied action."""
    row = await db.get(AIAction, action_id)
    if not row:
        return False, f"Action A{action_id} not found."
    if row.status == "suggested":
        row.status = "dismissed"
        row.decided_by = "human"
        await db.commit()
        return True, f"🚫 Dismissed A{action_id}."
    if row.status != "applied":
        return False, f"A{action_id} is '{row.status}' — nothing to undo."
    if not row.reversible:
        return False, f"A{action_id} is not reversible."
    summary = row.summary
    try:
        await _do_revert(db, row)
    except Exception as e:
        await db.rollback()
        return False, f"Could not undo A{action_id}: {e}"
    row = await db.get(AIAction, action_id)
    row.status = "reverted"
    row.reverted_at = _utcnow_naive()
    row.reverted_by = "human"
    await db.commit()
    return True, f"↩️ Undone A{action_id}: {summary}"


def _to_dict(r: AIAction) -> dict:
    return {
        "id": r.id, "action_type": r.action_type, "target_type": r.target_type,
        "target_id": r.target_id, "chain_id": r.chain_id, "project_id": r.project_id,
        "status": r.status, "decided_by": r.decided_by, "summary": r.summary,
        "reason": r.reason, "ai_reasoning": r.ai_reasoning,
        "before": r.before_state, "after": r.after_state, "reversible": r.reversible,
        "agreement_score": r.agreement_score, "error": r.error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "applied_at": r.applied_at.isoformat() if r.applied_at else None,
        "reverted_at": r.reverted_at.isoformat() if r.reverted_at else None,
        "reverted_by": r.reverted_by,
    }


async def list_actions(
    db: AsyncSession, limit: int = 50, status: Optional[str] = None,
    since_hours: Optional[int] = None,
) -> List[dict]:
    stmt = select(AIAction).order_by(AIAction.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(AIAction.status == status)
    if since_hours:
        stmt = stmt.where(AIAction.created_at >= _utcnow_naive() - timedelta(hours=since_hours))
    return [_to_dict(r) for r in (await db.execute(stmt)).scalars().all()]


async def autonomy_summary(db: AsyncSession) -> dict:
    since = _utcnow_naive() - timedelta(hours=24)
    rows = (await db.execute(
        select(AIAction.status, func.count()).where(AIAction.created_at >= since).group_by(AIAction.status)
    )).all()
    pending = (await db.execute(
        select(func.count()).select_from(AIAction).where(AIAction.status == "suggested")
    )).scalar() or 0
    return {
        "paused": is_ai_autonomy_paused(),
        "emergency_stop": is_emergency_stop(),
        "pending_suggestions": pending,
        "last_24h": {status: n for status, n in rows},
        "limits": {
            "adjustments_per_target_per_day": MAX_ADJUSTMENTS_PER_TARGET_PER_DAY,
            "gas_multiplier_range": [GAS_MULT_MIN, GAS_MULT_MAX],
            "gas_multiplier_step": GAS_MULT_STEP,
        },
    }
