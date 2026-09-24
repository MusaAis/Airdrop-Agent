import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import async_session
from backend.models import Project
from backend.ai.orchestrator import dual_ai_validate
from backend.ai.prompts import prompt_discovery
from backend.projects.blacklist import is_blacklisted
from backend.telegram.alerts import create_and_send_alert

logger = logging.getLogger("airdrop.discovery.processor")

async def process_discovery_results(raw_projects: list) -> int:
    """Returns the count of items actually sent through dual AI validation
    (i.e. excluding ones skipped for missing name or already blacklisted) —
    used by _run_discovery / the manual Telegram trigger to report a
    meaningful "X new projects validated" number, not just "N raw results".
    Previously this returned None, so callers had no way to know how many
    of the raw scraped results actually became something useful."""
    validated_count = 0
    async with async_session() as db:
        for raw in raw_projects:
            name = raw.get("name") or raw.get("project_name")
            if not name:
                continue
            if await is_blacklisted(db, name):
                continue
            try:
                validation = await dual_ai_validate(
                    task_type="discovery",
                    system_prompt="You are a crypto project analyst.",
                    user_prompt=prompt_discovery(str(raw)),
                    db=db
                )
                validated_count += 1
                if validation.agreement_score >= 80:
                    await create_and_send_alert(
                        type="new_project",
                        severity="info",
                        message=f"New potential airdrop: {name}\nAI confidence: {validation.agreement_score}%",
                    )
            except Exception as e:
                logger.error(f"Error processing discovery item {name}: {e}")
    return validated_count
