"""
Periodic Telegram reports (PLAN.md Phase 8), sent to their own group topics.

  daily / weekly / monthly  -> wallets (active vs not), tasks completed/failed/
                               skipped, gas, top projects, failure causes,
                               open alerts, plus the AI-written narrative
  ai                        -> AI activity: validations, autonomous actions,
                               suggestions waiting for you

Every number comes from a database query. The AI only narrates (via
reports/analyst.py) and the report is sent even if narration fails.
Plain text, no Markdown, so nothing in a project name can break the message.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models import (
    Wallet, Transaction, TaskFailure, Project, TaskConfig, TaskDailyProgress, Alert, AIValidation,
)
from backend.telegram.sender import send_telegram_message

logger = logging.getLogger("airdrop.reports.periodic")

KINDS = {
    "daily": (24, "Daily report"),
    "weekly": (168, "Weekly summary"),
    "monthly": (720, "Monthly summary"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)   # DB stores naive UTC


def _pretty(s: str) -> str:
    return (s or "").replace("_", " ")


async def _facts(db: AsyncSession, hours: int) -> dict:
    since = _now() - timedelta(hours=hours)

    wallet_rows = (await db.execute(select(Wallet.status, func.count()).group_by(Wallet.status))).all()
    wallets = {s: n for s, n in wallet_rows}
    gas_wallets = (await db.execute(
        select(func.count()).select_from(Wallet).where(Wallet.is_gas_wallet == True)
    )).scalar() or 0

    confirmed, gas_usd, wallets_active = (await db.execute(
        select(
            func.coalesce(func.sum(case((Transaction.status == "confirmed", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Transaction.status == "confirmed", Transaction.gas_cost_usd), else_=0)), 0),
            func.count(func.distinct(case((Transaction.status == "confirmed", Transaction.wallet_id)))),
        ).where(Transaction.created_at >= since)
    )).one()

    from backend.reports.gas_native import gas_native_totals, format_gas_native
    gas_native = await gas_native_totals(db, since=since)

    outcome_rows = (await db.execute(
        select(TaskFailure.outcome, func.count()).where(TaskFailure.created_at >= since).group_by(TaskFailure.outcome)
    )).all()
    outcomes = {o: n for o, n in outcome_rows}

    causes = (await db.execute(
        select(TaskFailure.category, func.count())
        .where(TaskFailure.outcome == "failed", TaskFailure.created_at >= since)
        .group_by(TaskFailure.category).order_by(func.count().desc()).limit(3)
    )).all()

    top_projects = (await db.execute(
        select(Project.name, func.count(Transaction.id))
        .select_from(Transaction)
        .join(TaskConfig, Transaction.task_config_id == TaskConfig.id)
        .join(Project, TaskConfig.project_id == Project.id)
        .where(Transaction.created_at >= since, Transaction.status == "confirmed")
        .group_by(Project.name).order_by(func.count(Transaction.id).desc()).limit(5)
    )).all()

    failing_projects = (await db.execute(
        select(Project.name, func.count(TaskFailure.id))
        .select_from(TaskFailure)
        .join(Project, TaskFailure.project_id == Project.id)
        .where(TaskFailure.outcome == "failed", TaskFailure.created_at >= since)
        .group_by(Project.name).order_by(func.count(TaskFailure.id).desc()).limit(3)
    )).all()

    today = _now().strftime("%Y-%m-%d")
    prog = (await db.execute(
        select(TaskDailyProgress.completed, TaskDailyProgress.daily_target).where(TaskDailyProgress.date == today)
    )).all()
    targets_met = sum(1 for c, t in prog if c >= t)

    tripped = [n for (n,) in (await db.execute(
        select(Project.name).where(Project.circuit_breaker_active == True)
    )).all()]
    alerts_open = (await db.execute(
        select(func.count()).select_from(Alert).where(Alert.resolved == False)
    )).scalar() or 0

    return {
        "wallets": wallets, "gas_wallets": int(gas_wallets), "wallets_active_in_window": int(wallets_active or 0),
        "completed": int(confirmed or 0), "failed": int(outcomes.get("failed", 0)),
        "skipped": int(outcomes.get("skipped", 0)), "gas_usd": round(float(gas_usd or 0), 2),
        "gas_native": {k: round(v, 8) for k, v in gas_native.items()}, "gas_native_text": format_gas_native(gas_native),
        "causes": [(c, n) for c, n in causes], "top_projects": [(p, n) for p, n in top_projects],
        "failing_projects": [(p, n) for p, n in failing_projects],
        "targets_met": targets_met, "targets_total": len(prog),
        "tripped": tripped, "alerts_open": int(alerts_open),
    }


def _render(kind: str, title: str, hours: int, f: dict, narrative: Optional[str]) -> str:
    icon = {"daily": "📊", "weekly": "🗓", "monthly": "📅"}[kind]
    w = f["wallets"]
    total_w = sum(w.values())
    active = w.get("active", 0)
    other = {k: v for k, v in w.items() if k != "active" and v}
    other_txt = f" ({', '.join(f'{v} {k}' for k, v in other.items())})" if other else ""
    done, failed = f["completed"], f["failed"]
    rate = f"{done / (done + failed) * 100:.1f}%" if (done + failed) else "n/a"

    lines = [
        f"{icon} {title} — {_now().strftime('%Y-%m-%d')} (last {hours // 24 if hours >= 48 else hours}{'d' if hours >= 48 else 'h'})",
        "",
        f"👛 Wallets: {total_w} total · {active} active · {total_w - active} not active{other_txt} · {f['gas_wallets']} gas wallet(s)",
        f"   {f['wallets_active_in_window']} wallet(s) completed at least one task in this period",
        "",
        f"✅ Tasks completed: {done}   ❌ failed: {failed}   ⏭ skipped: {f['skipped']}   success rate: {rate}",
        f"⛽ Gas spent: {f['gas_native_text']}",
    ]
    if f["top_projects"]:
        lines += ["", "📁 Most active projects: " + " · ".join(f"{p} {n}" for p, n in f["top_projects"])]
    if f["failing_projects"]:
        lines.append("⚠️ Most failures: " + " · ".join(f"{p} {n}" for p, n in f["failing_projects"]))
    if f["causes"]:
        lines.append("❗ Top failure causes: " + " · ".join(f"{_pretty(c)} {n}" for c, n in f["causes"]))
    if kind == "daily" and f["targets_total"]:
        lines += ["", f"🎯 Daily targets: {f['targets_met']}/{f['targets_total']} reached today"]
    if f["tripped"]:
        lines.append("🔴 Circuit breakers tripped: " + ", ".join(f["tripped"]))
    lines.append(f"🔔 Open alerts: {f['alerts_open']}")
    if narrative:
        lines += ["", "🧠 " + narrative.strip()]
    return "\n".join(lines)


async def _narrative(db: AsyncSession, hours: int) -> Optional[str]:
    try:
        from backend.reports.analyst import generate_daily_summary_narrative
        r = await generate_daily_summary_narrative(db, hours=hours)
        return r.get("narrative")
    except Exception as e:
        logger.warning("period report: narration skipped (%s)", e)
        return None


async def send_period_report(kind: str = "daily", db: Optional[AsyncSession] = None) -> str:
    hours, title = KINDS[kind]

    async def _run(s: AsyncSession) -> str:
        facts = await _facts(s, hours)
        text = _render(kind, title, hours, facts, await _narrative(s, hours))
        await send_telegram_message(text, parse_mode=None, topic=kind)
        return text

    if db is not None:
        return await _run(db)
    async with async_session() as s:
        return await _run(s)


# ── AI activity digest ───────────────────────────────────────────────────────
_STATUS_ICON = {"applied": "✅", "suggested": "🤔", "vetoed": "🚫", "reverted": "↩️",
                "dismissed": "❌", "expired": "⌛", "failed": "⚠️"}


async def build_ai_report(db: AsyncSession, hours: int = 24) -> str:
    from backend.core.autonomy import autonomy_summary, list_actions
    since = _now() - timedelta(hours=hours)

    s = await autonomy_summary(db)
    actions = await list_actions(db, limit=8, since_hours=hours)
    vals = (await db.execute(
        select(AIValidation.task_type, func.count(), func.avg(AIValidation.agreement_score))
        .where(AIValidation.created_at >= since).group_by(AIValidation.task_type)
    )).all()
    needs = (await db.execute(
        select(func.count()).select_from(AIValidation)
        .where(AIValidation.requires_human == True, AIValidation.resolved == False)
    )).scalar() or 0

    counts = s["last_24h"]
    lines = [
        f"🤖 AI activity — last {hours}h",
        "",
        f"Autonomy: {'🧊 FROZEN' if s['paused'] else '✅ active'}"
        + (" · 🔴 emergency stop" if s["emergency_stop"] else ""),
        "Autonomous actions: " + (" · ".join(f"{n} {k}" for k, n in counts.items()) or "none"),
    ]
    for a in actions:
        lines.append(f"  A{a['id']} {_STATUS_ICON.get(a['status'], '•')} {a['status']}: {a['summary']}")
    lines.append("")
    if vals:
        lines.append("Validations: " + " · ".join(
            f"{_pretty(t)} {n} (avg {round(avg or 0)}%)" for t, n, avg in vals))
    else:
        lines.append("Validations: none")
    lines.append(f"Waiting for your decision: {needs} validation(s), {s['pending_suggestions']} suggestion(s)")
    if needs or s["pending_suggestions"]:
        lines.append("→ /ai_pending")
    return "\n".join(lines)


async def send_ai_report(hours: int = 24, db: Optional[AsyncSession] = None) -> str:
    async def _run(s: AsyncSession) -> str:
        text = await build_ai_report(s, hours)
        await send_telegram_message(text, parse_mode=None, topic="ai")
        return text

    if db is not None:
        return await _run(db)
    async with async_session() as s:
        return await _run(s)
