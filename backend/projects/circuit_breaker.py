from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Project

async def increment_failure(db: AsyncSession, project: Project):
    project.consecutive_failures += 1
    if project.consecutive_failures >= 5 and not project.circuit_breaker_active:
        project.circuit_breaker_active = True
        project.status = "paused"  # auto-pause
    await db.commit()

async def reset_circuit(db: AsyncSession, project: Project):
    project.consecutive_failures = 0
    project.circuit_breaker_active = False
    if project.status == "paused":
        project.status = "active"
    await db.commit()
