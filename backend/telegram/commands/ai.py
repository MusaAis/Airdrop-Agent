import logging
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.ai")


def _action_ref(arg: str):
    """'A5' / 'a5' -> 5 (an autonomous-action id); anything else -> None
    (a plain number is an AIValidation id, as before Phase 6)."""
    a = (arg or "").strip()
    if a[:1] in ("A", "a") and a[1:].isdigit():
        return int(a[1:])
    return None


async def handle_ai_autonomy_off(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.core.autonomy import set_autonomy_paused
    await set_autonomy_paused(db, True, f"telegram:{user_id}")
    return (
        "🧊 AI autonomy frozen (saved — survives restarts). The AI will not make any autonomous "
        "changes until /ai_autonomy_on. Normal task execution and manual commands are unaffected."
    )


async def handle_ai_autonomy_on(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.core.autonomy import set_autonomy_paused
    await set_autonomy_paused(db, False, f"telegram:{user_id}")
    return "✅ AI autonomy resumed. It may pause wallets, tune gas multipliers and disable failing tasks again (within its limits)."


async def handle_ai_log(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    n = int(args[0]) if args else 10
    from backend.models import AIValidation
    from sqlalchemy import select, desc
    vals = (await db.execute(
        select(AIValidation).order_by(desc(AIValidation.created_at)).limit(n)
    )).scalars().all()
    if not vals:
        return "No AI validations recorded yet."
    lines = [f"🧠 Last {n} AI Validations:"]
    for v in vals:
        human = "⚠️ needs review" if v.requires_human and not v.resolved else "✅"
        lines.append(f"ID {v.id}: {v.task_type} | agreement={v.agreement_score}% | {human}")
    return "\n".join(lines)


async def handle_ai_validate(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: /ai_validate <project_id>"
    from backend.models import Project
    project = await db.get(Project, int(args[0]))
    if not project: return f"Project {args[0]} not found."
    try:
        from backend.ai.orchestrator import validate_project
        result = await validate_project(project)
        return f"✅ AI validation queued for {project.name}.\nConfidence: {result.get('confidence','?')}%"
    except Exception as e:
        return f"❌ Validation error: {e}"


async def handle_ai_approve(user_id, args, db, confirmation=None):
    """/ai_approve <validation_id>  — approve an AI validation
       /ai_approve A<id>            — apply an AI-suggested autonomous action"""
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: /ai_approve <validation_id>  or  /ai_approve A<action_id>"
    ref = _action_ref(args[0])
    if ref is not None:
        from backend.core.autonomy import approve_action
        _ok, msg = await approve_action(db, ref)
        return msg
    from backend.models import AIValidation
    val = await db.get(AIValidation, int(args[0]))
    if not val: return f"Validation {args[0]} not found."
    val.resolved = True
    val.human_decision = "approved"
    await db.commit()
    return f"✅ Validation {args[0]} approved."


async def handle_ai_reject(user_id, args, db, confirmation=None):
    """/ai_reject <validation_id>  — reject an AI validation
       /ai_reject A<id>            — dismiss an AI suggestion, or UNDO an applied autonomous action"""
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: /ai_reject <validation_id>  or  /ai_reject A<action_id>"
    ref = _action_ref(args[0])
    if ref is not None:
        from backend.core.autonomy import undo_action
        _ok, msg = await undo_action(db, ref)
        return msg
    from backend.models import AIValidation
    val = await db.get(AIValidation, int(args[0]))
    if not val: return f"Validation {args[0]} not found."
    val.resolved = True
    val.human_decision = "rejected"
    await db.commit()
    return f"❌ Validation {args[0]} rejected."


async def handle_ai_pending(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import AIValidation
    from backend.core.autonomy import list_actions
    from sqlalchemy import select
    pending = (await db.execute(
        select(AIValidation).where(AIValidation.requires_human == True, AIValidation.resolved == False)
    )).scalars().all()
    suggestions = await list_actions(db, limit=10, status="suggested")
    recent = await list_actions(db, limit=10, status="applied", since_hours=24)

    lines = []
    if pending:
        lines.append(f"⚠️ {len(pending)} validations need review:")
        for v in pending:
            lines.append(f"ID {v.id}: {v.task_type} | agreement={v.agreement_score}%")
        lines.append("Use /ai_approve <id> or /ai_reject <id>")
    if suggestions:
        if lines: lines.append("")
        lines.append(f"🤔 {len(suggestions)} AI suggestion(s) awaiting your approval:")
        for a in suggestions:
            lines.append(f"A{a['id']}: {a['summary']}")
        lines.append("Use /ai_approve A<id> or /ai_reject A<id>")
    if recent:
        if lines: lines.append("")
        lines.append("🤖 Autonomous actions in the last 24h (undo with /ai_reject A<id>):")
        for a in recent:
            lines.append(f"A{a['id']}: {a['summary']}")
    if not lines:
        return "✅ Nothing awaiting review, no autonomous actions in the last 24h."
    return "\n".join(lines)


async def handle_ai_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.config import GROQ_API_KEY, GEMINI_API_KEY
    groq_ok = "✅ set" if GROQ_API_KEY else "❌ missing"
    gemini_ok = "✅ set" if GEMINI_API_KEY else "❌ missing"
    from backend.models import AIValidation
    from backend.core.autonomy import autonomy_summary
    from sqlalchemy import select, func
    total = (await db.execute(select(func.count()).select_from(AIValidation))).scalar() or 0
    pending = (await db.execute(
        select(func.count()).select_from(AIValidation).where(
            AIValidation.requires_human == True, AIValidation.resolved == False
        )
    )).scalar() or 0
    s = await autonomy_summary(db)
    state = "🧊 FROZEN" if s["paused"] else "✅ active"
    counts = s["last_24h"]
    acts = ", ".join(f"{n} {k}" for k, n in counts.items()) or "none"
    return (
        f"🧠 AI Status\n"
        f"Groq API: {groq_ok}\n"
        f"Gemini API: {gemini_ok}\n"
        f"Total validations: {total}\n"
        f"Pending review: {pending}\n"
        f"Autonomy: {state}\n"
        f"Autonomous actions (24h): {acts}\n"
        f"Suggestions awaiting approval: {s['pending_suggestions']}"
    )


async def handle_ai_agreement(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    n = int(args[0]) if args else 10
    from backend.models import AIValidation
    from sqlalchemy import select, desc, func
    vals = (await db.execute(
        select(AIValidation).order_by(desc(AIValidation.created_at)).limit(n)
    )).scalars().all()
    if not vals:
        return "No validations recorded yet."
    scores = [v.agreement_score for v in vals if v.agreement_score is not None]
    avg = round(sum(scores) / len(scores)) if scores else 0
    lines = [f"🧠 Agreement scores (last {n}): avg {avg}%"]
    for v in vals:
        bar = "█" * (v.agreement_score // 10) if v.agreement_score else "?"
        lines.append(f"ID {v.id}: {v.task_type} [{bar}] {v.agreement_score}%")
    return "\n".join(lines)
