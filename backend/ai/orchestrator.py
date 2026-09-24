"""
AI Orchestrator — dual-model validation for discovery, risk, criteria, etc.

Role split (free-tier budget aware):
  Gemini  → PRIMARY analyst   (discovery, natural language, high-token tasks)
  Groq    → VALIDATOR         (fast structured JSON cross-check)

Agreement scoring — KEY INSIGHT:
  We only compare DECISION FIELDS, not prose/text fields.
  Two AIs will never produce identical strings for "description" or "evidence".
  Comparing those would always give low agreement scores.
  We compare: status, recommendation, overall_confidence range, approved, risk tier.

dual_ai_validate():
  1. Run Gemini (primary) + Groq (validator) concurrently
  2. Compare only the critical decision fields
  3. agreement >= 70 → trust Gemini output, auto-proceed
     agreement < 70  → flag requires_human=True, send to Telegram
  4. Groq 429/failure → Gemini-only with synthetic score 60, requires_human=True

single_gemini_validate():
  Gemini-only — used for pre-screening to save Groq quota.
"""

import asyncio
import hashlib
import json
import logging
import re
from typing import Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.gemini_client import ask_gemini
from backend.ai.groq_client import ask_groq
from backend.models import AIValidation

logger = logging.getLogger("airdrop.ai.orchestrator")

# Fields we actually compare to compute agreement.
# These are the decision fields — not prose, not evidence, not descriptions.
_DECISION_FIELDS = {
    "status",                # active/upcoming/stale/completed/dead
    "recommendation",        # FARM/MONITOR/SKIP
    "approved",              # true/false (config validation)
    "kyc_required",          # true/false/null
    "overall_confidence",    # 0-100 (we bucket into low/med/high)
    "risk_level",            # low/medium/high/critical
}

# Confidence buckets — "72" and "68" are both "medium", don't count as a conflict
def _confidence_bucket(val) -> str:
    try:
        n = int(val)
        if n < 40:
            return "low"
        if n < 70:
            return "medium"
        return "high"
    except Exception:
        return str(val)


def _strip_fences(raw: str) -> str:
    return re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()


def _safe_parse(raw: str) -> dict:
    try:
        return json.loads(_strip_fences(raw))
    except Exception:
        return {"raw_unparseable": raw[:200]}


def _extract_decisions(parsed: dict) -> dict:
    """Pull only the decision fields from a parsed AI output."""
    decisions = {}
    for field in _DECISION_FIELDS:
        val = parsed.get(field)
        if val is None:
            continue
        if field == "overall_confidence":
            decisions[field] = _confidence_bucket(val)
        else:
            decisions[field] = str(val).lower().strip()
    return decisions


def compare_outputs(out_a: dict, out_b: dict) -> Tuple[int, list]:
    """
    Compare ONLY decision fields between two AI outputs.
    Returns (agreement_pct, conflict_list).

    If neither output has any decision fields (e.g. both returned prose),
    we can't compute agreement — return (50, []) as neutral.
    """
    dec_a = _extract_decisions(out_a)
    dec_b = _extract_decisions(out_b)

    all_keys = set(dec_a.keys()) | set(dec_b.keys())
    if not all_keys:
        return 50, []

    matches = 0
    conflicts = []
    for key in all_keys:
        val_a = dec_a.get(key)
        val_b = dec_b.get(key)
        if val_a is None or val_b is None:
            # One model didn't produce this field — partial match
            matches += 0.5
        elif val_a == val_b:
            matches += 1
        else:
            conflicts.append({
                "field": key,
                "gemini": val_a,
                "groq": val_b,
            })

    agreement = int((matches / len(all_keys)) * 100)
    return agreement, conflicts


async def dual_ai_validate(
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    db: AsyncSession,
    # Legacy kwargs kept for backward-compat — ignored (roles are now fixed)
    model_a_func=None,
    model_b_func=None,
) -> AIValidation:
    """
    Run Gemini (primary) + Groq (validator) concurrently.
    Falls back to Gemini-only if Groq is rate-limited.
    """
    input_hash = hashlib.sha256(user_prompt.encode()).hexdigest()

    # ── Concurrent run ───────────────────────────────────────────────────────
    results = await asyncio.gather(
        ask_gemini(system_prompt, user_prompt),
        ask_groq(system_prompt, user_prompt),
        return_exceptions=True,
    )
    gemini_result, groq_result = results

    if isinstance(gemini_result, Exception):
        logger.error("Gemini failed in dual_ai_validate[%s]: %s", task_type, gemini_result)
        gemini_json = {}
    else:
        gemini_json = _safe_parse(gemini_result)

    groq_failed = isinstance(groq_result, Exception)
    if groq_failed:
        logger.warning(
            "Groq failed in dual_ai_validate[%s] (degrading to Gemini-only): %s",
            task_type, groq_result,
        )
        groq_json = {}
    else:
        groq_json = _safe_parse(groq_result)

    # ── Agreement scoring ────────────────────────────────────────────────────
    if groq_failed or not groq_json:
        agreement_score = 60
        conflicts = [{"field": "_groq", "gemini": "ok", "groq": "failed/unavailable"}]
        requires_human = True
        final_decision = gemini_json
    else:
        agreement_score, conflicts = compare_outputs(gemini_json, groq_json)
        requires_human = agreement_score < 70 or bool(conflicts)
        final_decision = gemini_json if agreement_score >= 70 else {}

    logger.info(
        "dual_ai_validate[%s]: agreement=%d%% conflicts=%d requires_human=%s",
        task_type, agreement_score, len(conflicts), requires_human,
    )

    validation = AIValidation(
        task_type=task_type,
        input_hash=input_hash,
        groq_output=groq_json,
        gemini_output=gemini_json,
        agreement_score=agreement_score,
        conflict_fields=conflicts,
        final_decision=final_decision,
        requires_human=requires_human,
        resolved=False,
    )
    db.add(validation)
    await db.commit()
    await db.refresh(validation)
    return validation


async def single_gemini_validate(
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    db: AsyncSession,
) -> AIValidation:
    """
    Gemini-only validation — used for pre-screening to preserve Groq quota.
    """
    input_hash = hashlib.sha256(user_prompt.encode()).hexdigest()
    try:
        raw = await ask_gemini(system_prompt, user_prompt)
        result_json = _safe_parse(raw)
    except Exception as e:
        logger.error("single_gemini_validate[%s] failed: %s", task_type, e)
        result_json = {}

    # For pre-screen we use overall_confidence as the agreement proxy
    confidence = result_json.get("overall_confidence", 0)
    try:
        score = int(confidence)
    except (ValueError, TypeError):
        score = 0

    validation = AIValidation(
        task_type=task_type,
        input_hash=input_hash,
        groq_output={},
        gemini_output=result_json,
        agreement_score=score,
        conflict_fields=[],
        final_decision=result_json,
        requires_human=score < 70,
        resolved=False,
    )
    db.add(validation)
    await db.commit()
    await db.refresh(validation)
    return validation
