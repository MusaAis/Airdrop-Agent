from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Project, TaskConfig, ProjectCriteria, ProjectContract, TaskDailyProgress, TaskSchedule
from typing import List, Optional
from datetime import datetime, timezone
import json

async def create_project(db: AsyncSession, **kwargs) -> Project:
    project = Project(**kwargs)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project

async def get_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    return await db.get(Project, project_id)

async def list_projects(db: AsyncSession, status: Optional[str] = None, include_archived: bool = False) -> List[Project]:
    """
    By default, archived projects are excluded from the normal list (Phase 4
    soft-delete) — they still exist in the DB for historical stats, they just
    don't clutter the day-to-day Projects tab. Pass include_archived=True (or
    status="archived" explicitly) to see them, e.g. for the future Phase 7
    stats dashboard.
    """
    stmt = select(Project)
    if status:
        stmt = stmt.where(Project.status == status)
    elif not include_archived:
        stmt = stmt.where(Project.status != "archived")
    result = await db.execute(stmt)
    return result.scalars().all()

async def update_project(db: AsyncSession, project_id: int, **kwargs):
    project = await db.get(Project, project_id)
    if not project:
        return None
    for key, value in kwargs.items():
        if hasattr(project, key):
            setattr(project, key, value)
    await db.commit()
    return project

async def delete_project(db: AsyncSession, project_id: int) -> bool:
    """
    Hard delete — kept for internal/administrative use, but the website and
    Telegram commands should call archive_project() instead (Phase 4: Musa
    wants deleted projects to remain in the historical record). This function
    is not wired to any route as of Phase 4; left in place in case a genuine
    hard-delete tool is needed later (e.g. a mistakenly-created test project).
    """
    project = await db.get(Project, project_id)
    if not project:
        return False
    await db.delete(project)
    await db.commit()
    return True

# --- Phase 4: soft archive / restore ---

async def archive_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    """
    Soft-delete: sets status to 'archived' and stamps archived_at. The row,
    its tasks, criteria, contracts, and transaction history are all left
    exactly as they are — nothing is removed. queue_manager.py's
    _project_is_dispatchable() already refuses to schedule tasks for any
    non-'active' status, so archiving also stops farming as a side effect,
    same as the existing project.pause behavior.
    """
    project = await db.get(Project, project_id)
    if not project:
        return None
    project.status = "archived"
    project.archived_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)
    return project

async def restore_project(db: AsyncSession, project_id: int, restore_to_status: str = "active") -> Optional[Project]:
    """Undo archive_project(). Does not touch eligibility_status — a
    restored project that was already declared eligible/not_eligible stays
    declared; restoring only affects the archived/active lifecycle."""
    project = await db.get(Project, project_id)
    if not project:
        return None
    project.status = restore_to_status
    project.archived_at = None
    await db.commit()
    await db.refresh(project)
    return project

async def stop_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    """Deliberate manual halt, distinct from archive (still visible in the
    default list, not hidden) and distinct from the circuit breaker's
    'paused' (this is intentional, not failure-triggered)."""
    return await update_project(db, project_id, status="stopped")

# --- Phase 4: eligibility declaration (website-only, see AddProject.jsx /
# Projects.jsx; Telegram only reads this via project.status, never sets it) ---

async def declare_eligibility(
    db: AsyncSession,
    project_id: int,
    eligible: bool,
    value_usd: Optional[float] = None,
) -> Optional[Project]:
    """
    Declares a project's airdrop outcome. Once declared (either True or
    False), queue_manager.py stops scheduling new tasks for this project
    regardless of its `status` — there is nothing left to farm for once the
    outcome is known. This is a one-time-per-decision action from the
    dashboard; clear_eligibility() below exists in case of a mis-click.
    """
    project = await db.get(Project, project_id)
    if not project:
        return None
    project.eligibility_status = "eligible" if eligible else "not_eligible"
    project.eligibility_value_usd = value_usd if eligible else None
    project.eligibility_declared_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)
    return project

async def clear_eligibility(db: AsyncSession, project_id: int) -> Optional[Project]:
    """Resets eligibility back to 'pending' — e.g. correcting a mis-click.
    Farming resumes automatically on the next queue fill if status is still
    'active' and nothing else is blocking it."""
    project = await db.get(Project, project_id)
    if not project:
        return None
    project.eligibility_status = "pending"
    project.eligibility_value_usd = None
    project.eligibility_declared_at = None
    await db.commit()
    await db.refresh(project)
    return project

# Task Config management
async def create_task_config(db: AsyncSession, **kwargs) -> TaskConfig:
    task = TaskConfig(**kwargs)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task

async def list_task_configs(db: AsyncSession, project_id: Optional[int] = None) -> List[TaskConfig]:
    stmt = select(TaskConfig)
    if project_id:
        stmt = stmt.where(TaskConfig.project_id == project_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_task_config(db: AsyncSession, task_id: int) -> Optional[TaskConfig]:
    return await db.get(TaskConfig, task_id)

async def update_task_config(db: AsyncSession, task_id: int, **kwargs):
    task = await db.get(TaskConfig, task_id)
    if not task:
        return None
    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)
    await db.commit()
    return task

async def delete_task_config(db: AsyncSession, task_id: int) -> bool:
    task = await db.get(TaskConfig, task_id)
    if not task:
        return False
    await db.delete(task)
    await db.commit()
    return True

# Daily progress
async def get_daily_progress(db: AsyncSession, wallet_id: int, project_id: int, task_config_id: int, date_str: str) -> Optional[TaskDailyProgress]:
    stmt = select(TaskDailyProgress).where(
        TaskDailyProgress.wallet_id == wallet_id,
        TaskDailyProgress.project_id == project_id,
        TaskDailyProgress.task_config_id == task_config_id,
        TaskDailyProgress.date == date_str
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
