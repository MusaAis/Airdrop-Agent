from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import TaskDailyProgress, Wallet, Project, TaskConfig
from datetime import datetime, timezone

async def get_daily_progress_report(db: AsyncSession, project_id: int = None):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stmt = select(
        Wallet.address,
        Project.name,
        TaskConfig.task_type,
        TaskDailyProgress.daily_target,
        TaskDailyProgress.completed
    ).join(TaskDailyProgress, TaskDailyProgress.wallet_id == Wallet.id)\
     .join(TaskConfig, TaskDailyProgress.task_config_id == TaskConfig.id)\
     .join(Project, TaskDailyProgress.project_id == Project.id)\
     .where(TaskDailyProgress.date == today_str)

    if project_id:
        stmt = stmt.where(Project.id == project_id)

    result = await db.execute(stmt)
    rows = result.all()
    return [{
        "wallet": r.address,
        "project": r.name,
        "task_type": r.task_type,
        "completed": r.completed,
        "target": r.daily_target,
        "remaining": max(0, r.daily_target - r.completed)
    } for r in rows]
