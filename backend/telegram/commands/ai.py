import logging
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.ai")


async def handle_ai_autonomy_off(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.core.kill_switch import set_ai_autonomy_paused
    set_ai_autonomy_paused(True)
    return (
        "🧊 AI autonomy frozen. The AI-managed task/wallet engine will not make "
        "any autonomous changes until /ai_autonomy_on. Normal task execution "
        "and manual commands are unaffected."
    )


async def handle_ai_autonomy_on(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.core.kill_switch import set_ai_autonomy_paused
    set_ai_autonomy_paused(False)
    return "✅ AI autonomy resumed. The AI-managed task/wallet engine may act autonomously again."


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
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: /ai_approve <validation_id>"
    from backend.models import AIValidation
    val = await db.get(AIValidation, int(args[0]))
    if not val: return f"Validation {args[0]} not found."
    val.resolved = True
    val.human_decision = "approved"
    await db.commit()
    return f"✅ Validation {args[0]} approved."


async def handle_ai_reject(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: /ai_reject <validation_id>"
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
    from sqlalchemy import select
    pending = (await db.execute(
        select(AIValidation).where(AIValidation.requires_human == True, AIValidation.resolved == False)
    )).scalars().all()
    if not pending:
        return "✅ No validations awaiting human review."
    lines = [f"⚠️ {len(pending)} validations need review:"]
    for v in pending:
        lines.append(f"ID {v.id}: {v.task_type} | agreement={v.agreement_score}%")
    lines.append("\nUse /ai_approve <id> or /ai_reject <id>")
    return "\n".join(lines)


async def handle_ai_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.config import GROQ_API_KEY, GEMINI_API_KEY
    groq_ok = "✅ set" if GROQ_API_KEY else "❌ missing"
    gemini_ok = "✅ set" if GEMINI_API_KEY else "❌ missing"
    from backend.models import AIValidation
    from sqlalchemy import select, func
    total = (await db.execute(select(func.count()).select_from(AIValidation))).scalar() or 0
    pending = (await db.execute(
        select(func.count()).select_from(AIValidation).where(
            AIValidation.requires_human == True, AIValidation.resolved == False
        )
    )).scalar() or 0
    return (
        f"🧠 AI Status\n"
        f"Groq API: {groq_ok}\n"
        f"Gemini API: {gemini_ok}\n"
        f"Total validations: {total}\n"
        f"Pending review: {pending}"
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
