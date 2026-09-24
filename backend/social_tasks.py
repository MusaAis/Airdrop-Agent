"""
Social task tracking.
Social tasks (Discord, Twitter, form submissions) are tracked manually —
the agent records completion status per wallet per project per task type.
These are never automated via Telegram (ToS risk) but are tracked in the
eligibility dashboard and counted toward overall protocol eligibility %.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, Text, Boolean, DateTime, ForeignKey
from backend.database import Base
from backend.models import Wallet, Project

logger = logging.getLogger("airdrop.social")


class SocialTask(Base):
    """Per-wallet per-protocol social task completion record."""
    __tablename__ = "social_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    # twitter_follow / discord_join / discord_role / form_submit / telegram_join / waitlist_signup
    description: Mapped[str] = mapped_column(Text, default="")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def mark_social_complete(
    db: AsyncSession,
    wallet_id: int,
    project_id: int,
    task_type: str,
    notes: str = "",
) -> SocialTask:
    """Mark a social task as completed for a wallet."""
    # Check if record exists
    result = await db.execute(
        select(SocialTask).where(
            SocialTask.wallet_id == wallet_id,
            SocialTask.project_id == project_id,
            SocialTask.task_type == task_type,
        )
    )
    record = result.scalar_one_or_none()

    if record:
        record.completed = True
        record.completed_at = datetime.now(timezone.utc)
        record.notes = notes
    else:
        record = SocialTask(
            wallet_id=wallet_id,
            project_id=project_id,
            task_type=task_type,
            completed=True,
            completed_at=datetime.now(timezone.utc),
            notes=notes,
        )
        db.add(record)

    await db.commit()
    await db.refresh(record)
    logger.info(f"Social task completed: wallet={wallet_id} project={project_id} type={task_type}")
    return record


async def get_social_progress(
    db: AsyncSession, project_id: int, wallet_id: Optional[int] = None
) -> List[dict]:
    """Get social task completion status per wallet (or specific wallet) for a project."""
    stmt = select(SocialTask).where(SocialTask.project_id == project_id)
    if wallet_id:
        stmt = stmt.where(SocialTask.wallet_id == wallet_id)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [
        {
            "wallet_id": t.wallet_id,
            "project_id": t.project_id,
            "task_type": t.task_type,
            "completed": t.completed,
            "completed_at": str(t.completed_at) if t.completed_at else None,
            "notes": t.notes,
        }
        for t in tasks
    ]


async def list_wallet_social_tasks(db: AsyncSession, wallet_id: int) -> List[dict]:
    """All social tasks for a specific wallet across all projects."""
    result = await db.execute(
        select(SocialTask).where(SocialTask.wallet_id == wallet_id)
    )
    tasks = result.scalars().all()
    return [
        {
            "project_id": t.project_id,
            "task_type": t.task_type,
            "completed": t.completed,
            "completed_at": str(t.completed_at) if t.completed_at else None,
        }
        for t in tasks
    ]


SOCIAL_TASK_TYPES = [
    "twitter_follow",
    "twitter_retweet",
    "discord_join",
    "discord_role",
    "form_submit",
    "telegram_join",
    "waitlist_signup",
    "kyc_submitted",
]

