"""
AI analyst / reporting layer (PLAN.md §5.2).

Design choice, deviating from the plan's suggestion to reuse dual_ai_validate:
dual_ai_validate's agreement scoring compares structured DECISION fields
(status/approved/risk_level/etc — see ai/orchestrator.py _DECISION_FIELDS). A
narrated summary is prose with no decision fields, so agreement scoring would
always fall through to the neutral 50%/requires_human=True path — which would
incorrectly dump every daily summary into /ai_pending for approval. A summary
isn't a decision that needs approving; it's a report.

Instead:
  - Trend/anomaly detection is done in plain Python against real DB numbers
    (this module never asks the LLM to compute a number, only to narrate ones
    we already computed — keeps it factual, matches the project's existing
    "AI never invents thresholds" principle from prompt_criteria).
  - Narration uses ask_gemini with ask_groq as fallback (same primary/fallback
    role split as nl_parser.py), NOT dual_ai_validate.
  - We still write an AIValidation row with task_type="analyst_summary" so the
    summary shows up in the AI Log / ai_status counters, matching the project's
    existing habit of logging all AI calls in one place. agreement_score is a
    simple availability signal here (100 = both models reachable, 50 = only
    one), NOT a correctness measure, and requires_human is always False since
    there is nothing to approve.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.models import (
    Transaction, TaskDailyProgress, Project, Wallet, AIValidation, Alert,
)
from backend.ai.gemini_client import ask_gemini
from backend.ai.groq_client import ask_groq
from backend.ai.date_injector import get_date_prefix

logger = logging.getLogger("airdrop.reports.analyst")

# Trend thresholds — a metric moving beyond these vs. its 7-day baseline
# gets flagged for the narrative to call out explicitly, rather than relying
# on the LLM to "notice" it in a wall of numbers.
FAILURE_RATE_FLAG_DELTA = 0.15   # +15 percentage points vs 7d baseline
GAS_COST_FLAG_MULTIPLIER = 1.5   # 1.5x the 7d daily average


async def _gather_facts(db: AsyncSession, hours: int = 24) -> dict:
    """Pure data gathering — no AI, no interpretation. Every number here is a
    real query result; the LLM is only ever shown this dict, never asked to
    produce numbers of its own."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    baseline_since = now - timedelta(days=8)  # 7 days before the "since" window

    # Recent-window tx stats
    recent_txs = (await db.execute(
        select(Transaction).where(Transaction.created_at >= since)
    )).scalars().all()
    recent_total = len(recent_txs)
    recent_failed = sum(1 for t in recent_txs if t.status == "failed")
    recent_confirmed = sum(1 for t in recent_txs if t.status == "confirmed")
    recent_gas_usd = sum(t.gas_cost_usd or 0 for t in recent_txs if t.status == "confirmed")
    recent_failure_rate = (recent_failed / recent_total) if recent_total else 0.0

    # 7-day baseline (excludes the most recent window itself)
    baseline_txs = (await db.execute(
        select(Transaction).where(
            Transaction.created_at >= baseline_since,
            Transaction.created_at < since,
        )
    )).scalars().all()
    baseline_days = 7
    baseline_total = len(baseline_txs)
    baseline_failed = sum(1 for t in baseline_txs if t.status == "failed")
    baseline_gas_usd = sum(t.gas_cost_usd or 0 for t in baseline_txs if t.status == "confirmed")
    baseline_failure_rate = (baseline_failed / baseline_total) if baseline_total else 0.0
    baseline_avg_daily_gas = (baseline_gas_usd / baseline_days) if baseline_days else 0.0

    # Failure reasons (top clusters in the recent window)
    reason_counts: dict = {}
    for t in recent_txs:
        if t.status == "failed" and t.error_message:
            key = t.error_message[:80]
            reason_counts[key] = reason_counts.get(key, 0) + 1
    top_failures = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    # Daily target shortfalls (today only)
    today_str = now.strftime("%Y-%m-%d")
    progress_rows = (await db.execute(
        select(TaskDailyProgress).where(TaskDailyProgress.date == today_str)
    )).scalars().all()
    shortfalls = [
        {"wallet_id": p.wallet_id, "project_id": p.project_id,
         "completed": p.completed, "target": p.daily_target}
        for p in progress_rows if p.completed < p.daily_target
    ]

    # Circuit breakers currently tripped
    tripped_projects = (await db.execute(
        select(Project).where(Project.circuit_breaker_active == True)
    )).scalars().all()

    # Sybil flags raised in the window
    sybil_alerts = (await db.execute(
        select(Alert).where(Alert.type == "sybil_flag", Alert.created_at >= since)
    )).scalars().all()

    # Wallets that went into cooldown in the window (failure-driven)
    cooldown_wallets = (await db.execute(
        select(func.count()).select_from(Wallet).where(Wallet.status == "cooldown")
    )).scalar() or 0

    facts = {
        "window_hours": hours,
        "tx_total": recent_total,
        "tx_confirmed": recent_confirmed,
        "tx_failed": recent_failed,
        "failure_rate_pct": round(recent_failure_rate * 100, 1),
        "gas_spent_usd": round(recent_gas_usd, 2),
        "top_failure_reasons": [{"reason": r, "count": c} for r, c in top_failures],
        "daily_target_shortfalls": shortfalls[:20],
        "shortfall_count": len(shortfalls),
        "circuit_breakers_tripped": [{"id": p.id, "name": p.name} for p in tripped_projects],
        "sybil_alerts_count": len(sybil_alerts),
        "wallets_in_cooldown": cooldown_wallets,
    }

    # Deterministic trend flags — computed here, not left for the LLM to spot.
    flags = []
    if baseline_total >= 20:  # only flag once we have a meaningful baseline
        delta = recent_failure_rate - baseline_failure_rate
        if delta >= FAILURE_RATE_FLAG_DELTA:
            flags.append(
                f"Failure rate is up {delta*100:.1f} percentage points vs the "
                f"7-day baseline ({recent_failure_rate*100:.1f}% vs {baseline_failure_rate*100:.1f}%)."
            )
    if baseline_avg_daily_gas > 0:
        window_days = max(hours / 24, 0.01)
        recent_daily_gas = recent_gas_usd / window_days
        if recent_daily_gas >= baseline_avg_daily_gas * GAS_COST_FLAG_MULTIPLIER:
            flags.append(
                f"Gas spend is running at ~${recent_daily_gas:.2f}/day, "
                f"{recent_daily_gas / baseline_avg_daily_gas:.1f}x the 7-day average of ${baseline_avg_daily_gas:.2f}/day."
            )
    facts["trend_flags"] = flags
    return facts


_SUMMARY_SYSTEM_PROMPT = (
    "You are writing a short operational summary for the operator of an "
    "automated crypto airdrop-farming testnet agent. You will be given a JSON "
    "fact pack — every number in it is already computed and verified. "
    "Your job is ONLY to narrate these facts in plain, direct language. "
    "Rules:\n"
    "- Never invent, estimate, or round differently any number not present in the fact pack.\n"
    "- If a field is empty or zero, say so briefly rather than skipping it silently.\n"
    "- 3-6 short sentences or bullet points. No headers, no markdown tables.\n"
    "- If trend_flags is non-empty, lead with those — they are the most important thing to surface.\n"
    "- Do not suggest specific configuration changes; just describe what happened and let the operator decide."
)


def _build_user_prompt(facts: dict) -> str:
    import json
    return f"{get_date_prefix()}\n\nFACT PACK:\n{json.dumps(facts, indent=2)}\n\nWrite the summary now."


async def generate_daily_summary_narrative(db: AsyncSession, hours: int = 24) -> dict:
    """
    Returns {"narrative": str|None, "facts": dict, "validation_id": int|None,
    "error": str|None}. Never raises — callers (scheduler, Telegram, API)
    should fall back to the plain factual summary if narrative is None.
    """
    facts = await _gather_facts(db, hours)
    user_prompt = _build_user_prompt(facts)

    gemini_text: Optional[str] = None
    groq_text: Optional[str] = None
    error = None

    try:
        gemini_text = await ask_gemini(_SUMMARY_SYSTEM_PROMPT, user_prompt, temperature=0.3)
    except Exception as e:
        logger.warning("analyst summary: Gemini failed (%s), trying Groq", e)
        try:
            groq_text = await ask_groq(_SUMMARY_SYSTEM_PROMPT, user_prompt, temperature=0.3)
        except Exception as e2:
            logger.error("analyst summary: both Gemini and Groq failed: %s / %s", e, e2)
            error = f"AI narration unavailable: {e2}"

    narrative = gemini_text or groq_text

    # Log into AIValidation for the AI Log page / ai_status counters, per the
    # module docstring — availability signal, not a correctness/approval gate.
    validation_id = None
    try:
        # Groq only ever runs as a fallback when Gemini fails, so both text
        # variables are never both truthy — this is an availability signal
        # (was the narration produced at all, by either provider), not a
        # cross-model agreement score.
        agreement = 100 if gemini_text else (50 if groq_text else 0)
        validation = AIValidation(
            task_type="analyst_summary",
            input_hash="n/a",
            groq_output={"text": groq_text} if groq_text else {},
            gemini_output={"text": gemini_text} if gemini_text else {},
            agreement_score=agreement,
            conflict_fields=[],
            final_decision={"narrative": narrative} if narrative else {},
            requires_human=False,
            resolved=True,  # nothing to approve — mark resolved so it never
                             # shows up in /ai_pending
        )
        db.add(validation)
        await db.commit()
        await db.refresh(validation)
        validation_id = validation.id
    except Exception as e:
        logger.error("Failed to log analyst_summary AIValidation: %s", e)

    return {
        "narrative": narrative,
        "facts": facts,
        "validation_id": validation_id,
        "error": error,
    }


def format_plain_fallback(facts: dict) -> str:
    """Plain-text rendering used when AI narration is unavailable — the
    daily summary must never go out empty just because both AI providers
    are down."""
    lines = [
        f"Txs: {facts['tx_total']} total, {facts['tx_confirmed']} confirmed, "
        f"{facts['tx_failed']} failed ({facts['failure_rate_pct']}% failure rate).",
        f"Gas spent: ${facts['gas_spent_usd']}.",
    ]
    if facts["shortfall_count"]:
        lines.append(f"{facts['shortfall_count']} wallet/task targets behind today.")
    if facts["circuit_breakers_tripped"]:
        names = ", ".join(p["name"] for p in facts["circuit_breakers_tripped"])
        lines.append(f"Circuit breakers tripped: {names}.")
    if facts["wallets_in_cooldown"]:
        lines.append(f"{facts['wallets_in_cooldown']} wallet(s) in cooldown.")
    if facts["sybil_alerts_count"]:
        lines.append(f"{facts['sybil_alerts_count']} Sybil alert(s) raised.")
    for flag in facts.get("trend_flags", []):
        lines.append(f"⚠️ {flag}")
    return "\n".join(lines)
