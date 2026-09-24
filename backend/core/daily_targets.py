import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import TaskConfig, TaskDailyProgress

async def get_or_create_daily_target(
    db: AsyncSession,
    wallet_id: int,
    wallet_address: str,
    project_id: int,
    task_config: TaskConfig,
    date_str: str,
) -> TaskDailyProgress:
    """Seed uses wallet_address (not wallet_id) per MASTER_PLAN §5.8."""
    stmt = select(TaskDailyProgress).where(
        TaskDailyProgress.wallet_id == wallet_id,
        TaskDailyProgress.project_id == project_id,
        TaskDailyProgress.task_config_id == task_config.id,
        TaskDailyProgress.date == date_str
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()
    if not progress:
        seed_str = f"{wallet_address}{project_id}{date_str}"
        seed = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16) % 10000
        daily_range = task_config.daily_tx_max - task_config.daily_tx_min + 1
        target = task_config.daily_tx_min + (seed % daily_range)
        progress = TaskDailyProgress(
            wallet_id=wallet_id, project_id=project_id,
            task_config_id=task_config.id, date=date_str,
            daily_target=target, completed=0
        )
        db.add(progress)
        await db.commit()
        await db.refresh(progress)
    return progress
