import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.projects.manager import list_projects, get_project, create_project, update_project
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.project")

async def handle_project_list(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    projects = await list_projects(db)
    if not projects: return "No projects."
    return "\n".join(f"{p.id}: {p.name} [{p.type}] status:{p.status} priority:{p.priority}" for p in projects)

async def handle_project_add(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: project.add <name> <type (ecosystem/dapp)>"
    name, ptype = args[0], args[1]
    project = await create_project(db, name=name, type=ptype)
    return f"✅ Project {project.name} added (ID:{project.id})"

async def handle_project_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.status <id>"
    project = await get_project(db, int(args[0]))
    if not project: return "Project not found."
    return f"{project.name}: status={project.status} priority={project.priority}"

async def handle_project_disable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.disable <id>"
    if confirmation is None: return "⚠️ Confirm disable project? Reply 'confirm'"
    await update_project(db, int(args[0]), status="inactive")
    return "⚠️ Project disabled."

async def handle_project_enable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.enable <id>"
    await update_project(db, int(args[0]), status="active")
    return "✅ Project enabled."

async def handle_project_pause(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.pause <id>"
    if confirmation is None: return "⚠️ Confirm pause project? Reply 'confirm'"
    await update_project(db, int(args[0]), status="paused")
    return "⏸ Project paused."

async def handle_project_resume(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.resume <id>"
    await update_project(db, int(args[0]), status="active")
    return "▶ Project resumed."

async def handle_project_approve(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.approve <id>"
    project = await get_project(db, int(args[0]))
    if not project: return "Project not found."

    # Previously this just flipped status to "active" with no risk/ROI check
    # at all — task_type="risk" and task_type="roi" had prompts but nothing
    # ever called them automatically. The master plan's own cross-validation
    # rule table says risk assessment should only auto-proceed if BOTH AIs
    # say FARM; a split should set status to "monitor" and alert instead of
    # silently farming a project nobody actually risk-checked.
    from sqlalchemy import select
    from backend.models import ProjectCriteria
    from backend.ai.orchestrator import dual_ai_validate
    from backend.ai.prompts import prompt_risk, prompt_roi

    criteria = (await db.execute(select(ProjectCriteria).where(ProjectCriteria.project_id == project.id))).scalars().all()
    project_blob = (
        f"name: {project.name}\ntype: {project.type}\nwebsite: {project.website}\n"
        f"twitter: {project.twitter}\ndiscord: {project.discord}\n"
        f"criteria: {[c.description for c in criteria]}"
    )

    risk_validation = await dual_ai_validate(
        task_type="risk",
        system_prompt="You are a crypto security analyst assessing airdrop farming risk.",
        user_prompt=prompt_risk(project_blob),
        db=db,
    )
    roi_validation = await dual_ai_validate(
        task_type="roi",
        system_prompt="You are a crypto analyst estimating airdrop value. Be conservative.",
        user_prompt=prompt_roi(project_blob),
        db=db,
    )

    recommendation = (risk_validation.final_decision or {}).get("recommendation", "").upper()
    project.ai_confidence = risk_validation.agreement_score
    from datetime import datetime, timezone
    project.ai_last_verified = datetime.now(timezone.utc)

    if recommendation == "SKIP" or risk_validation.requires_human:
        project.status = "monitor"
        await db.commit()
        return (
            f"⚠️ '{project.name}' set to MONITOR, not active — risk check did not clearly pass "
            f"(recommendation: {recommendation or 'unclear'}, AI agreement {risk_validation.agreement_score}%). "
            f"Use /ai_pending to review, then project.approve again to override."
        )

    await update_project(db, project.id, status="active")
    return (
        f"✅ '{project.name}' approved and set active. "
        f"Risk: {recommendation or 'reviewed'} ({risk_validation.agreement_score}% agreement). "
        f"ROI logged — see /ai_log for the estimate."
    )

async def handle_project_reject(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.reject <id>"
    project = await get_project(db, int(args[0]))
    if not project: return "Project not found."
    await update_project(db, project.id, status="dead")
    return f"🚫 '{project.name}' rejected."

async def handle_project_farm(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.farm <id>"
    project = await get_project(db, int(args[0]))
    if not project: return "Project not found."
    await update_project(db, project.id, status="active")
    return f"🌾 '{project.name}' added to farming queue."

async def handle_project_prioritize(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 2: return "Usage: project.prioritize <id> <1-10>"
    await update_project(db, int(args[0]), priority=max(1, min(10, int(args[1]))))
    return f"✅ Priority set to {args[1]}."

async def handle_project_cap(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 2: return "Usage: project.cap <id> <max_wallets>"
    await update_project(db, int(args[0]), max_concurrent_wallets=int(args[1]))
    return f"✅ Max concurrent wallets set to {args[1]}."

async def handle_project_update(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.update <id>"
    project = await get_project(db, int(args[0]))
    if not project: return "Project not found."

    # Previously this just returned a string saying "Re-validation queued" —
    # nothing was actually queued or called. This is task_type="criteria"
    # (Prompt C), which had a working prompt and a working manual /ai/validate
    # path but no automatic trigger anywhere.
    from sqlalchemy import select
    from backend.models import ProjectCriteria
    from backend.ai.orchestrator import dual_ai_validate
    from backend.ai.prompts import prompt_criteria

    existing = (await db.execute(select(ProjectCriteria).where(ProjectCriteria.project_id == project.id))).scalars().all()
    previous_criteria = [c.description for c in existing]
    doc_blob = (
        f"name: {project.name}\nwebsite: {project.website}\ntwitter: {project.twitter}\n"
        f"discord: {project.discord}\nprevious_criteria: {previous_criteria}"
    )

    validation = await dual_ai_validate(
        task_type="criteria",
        system_prompt="You are extracting precise airdrop eligibility criteria. Accuracy is critical — this drives real transactions.",
        user_prompt=prompt_criteria(doc_blob, str(previous_criteria)),
        db=db,
    )

    if validation.requires_human:
        return (
            f"⚠️ Criteria re-check for '{project.name}' needs human review "
            f"(AI agreement {validation.agreement_score}%) — see /ai_pending."
        )
    return (
        f"✅ Criteria re-checked for '{project.name}' (AI agreement {validation.agreement_score}%). "
        f"See /ai_log for details, or project.criteria {project.id} for the current stored criteria."
    )

async def handle_project_criteria(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.criteria <id>"
    from backend.projects.criteria import list_criteria
    criteria = await list_criteria(db, int(args[0]))
    if not criteria: return "No criteria configured."
    return "\n".join(
        f"• [{c.type}] {c.description}" + (f" — {c.threshold} {c.unit or ''}" if c.threshold else "")
        + (" ⚠️" if c.uncertain else "")
        for c in criteria
    )

async def handle_project_gap(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.gap <id>"
    project = await get_project(db, int(args[0]))
    if not project: return "Project not found."

    # Previously this returned "sent to AI. Check ai.pending" without ever
    # calling dual_ai_validate — task_type="gap" never actually ran. This is
    # the exact feature behind "auto-config: don't show governance if this
    # project doesn't support it" — Prompt G already has an UNSUPPORTED
    # category with a governance example built in.
    from sqlalchemy import select
    from backend.models import ProjectCriteria
    from backend.projects.manager import list_task_configs
    from backend.ai.orchestrator import dual_ai_validate
    from backend.ai.prompts import prompt_gap
    import json

    criteria = (await db.execute(select(ProjectCriteria).where(ProjectCriteria.project_id == project.id))).scalars().all()
    task_configs = await list_task_configs(db, project.id)

    criteria_json = json.dumps([
        {"type": c.type, "description": c.description, "threshold": c.threshold, "unit": c.unit}
        for c in criteria
    ])
    task_config_json = json.dumps([
        {"id": t.id, "task_type": t.task_type, "enabled": t.enabled} for t in task_configs
    ])

    validation = await dual_ai_validate(
        task_type="gap",
        system_prompt="You are auditing task configuration against airdrop eligibility criteria.",
        user_prompt=prompt_gap(task_config_json, criteria_json),
        db=db,
    )

    decision = validation.final_decision or {}
    missing = decision.get("missing_tasks", [])
    unsupported = decision.get("unsupported_tasks", [])

    # Auto-apply the safe, reversible half of this: disable task configs the
    # AI says the project doesn't support (e.g. governance on a project with
    # no governance). Never auto-CREATE new tasks — that spends real gas, so
    # missing/required tasks still need an explicit task.enable or a new
    # task_config from you, surfaced below instead of applied silently.
    disabled_names = []
    if unsupported and not validation.requires_human:
        for u in unsupported:
            t_type = u.get("task_type")
            for t in task_configs:
                if t.task_type == t_type and t.enabled:
                    t.enabled = False
                    disabled_names.append(t_type)
        if disabled_names:
            await db.commit()

    lines = [f"🔍 Gap analysis for '{project.name}' (AI agreement {validation.agreement_score}%):"]
    if disabled_names:
        lines.append(f"🚫 Auto-disabled (project doesn't support): {', '.join(disabled_names)}")
    if missing:
        lines.append("⚠️ Missing required tasks (add manually):")
        for m in missing:
            lines.append(f"  • {m.get('criteria_description', m.get('suggested_task_type'))}")
    if not disabled_names and not missing:
        lines.append("✅ No gaps found — task config matches criteria.")
    if validation.requires_human:
        lines.append("⚠️ Low AI agreement — review manually via /ai_pending before trusting this.")
    return "\n".join(lines)

async def handle_project_blacklist(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.blacklist <name>"
    if confirmation is None: return f"⚠️ Blacklist '{args[0]}'? Reply 'confirm'"
    from backend.projects.blacklist import blacklist_project
    await blacklist_project(db, args[0], reason="manual", added_by="user")
    return f"🚫 '{args[0]}' blacklisted."

async def handle_project_circuit_breaker(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.circuit_breaker <id>"
    project = await get_project(db, int(args[0]))
    if not project: return "Project not found."
    status = "🔴 ACTIVE" if project.circuit_breaker_active else "🟢 OK"
    return f"Circuit breaker '{project.name}': {status}\nFailures: {project.consecutive_failures}/5"

async def handle_project_reset_circuit(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: project.reset_circuit <id>"
    project = await get_project(db, int(args[0]))
    if not project: return "Project not found."
    from backend.projects.circuit_breaker import reset_circuit
    await reset_circuit(db, project)
    return f"✅ Circuit breaker reset for '{project.name}'."
