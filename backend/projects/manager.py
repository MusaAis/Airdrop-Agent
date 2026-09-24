from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Project, TaskConfig, ProjectCriteria, ProjectContract, TaskDailyProgress, TaskSchedule
from typing import List, Optional
import json

async def create_project(db: AsyncSession, **kwargs) -> Project:
    project = Project(**kwargs)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project

async def get_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    return await db.get(Project, project_id)

async def list_projects(db: AsyncSession, status: Optional[str] = None) -> List[Project]:
    stmt = select(Project)
    if status:
        stmt = stmt.where(Project.status == status)
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
    project = await db.get(Project, project_id)
    if not project:
        return False
    await db.delete(project)
    await db.commit()
    return True

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

