import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base, async_session
from backend.models import AgentStatus

logger = logging.getLogger("airdrop.kill_switch")


class KillSwitchState(Base):
    """Single-row (id=1) persistence for the emergency stop and the global dry-run flag.

    Both used to live only in process memory, so a crash or redeploy silently turned the
    agent back to live trading with dry-run off. They are now restored at startup
    (see load_kill_switch_state) and written on every change."""
    __tablename__ = "kill_switch_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


async def _persist(db: AsyncSession, by: str, **fields) -> None:
    """Upsert the single state row. Does NOT commit: callers commit with their own changes."""
    row = await db.get(KillSwitchState, 1)
    if row is None:
        row = KillSwitchState(id=1, emergency_stop=False, dry_run=False)
        db.add(row)
    for k, v in fields.items():
        setattr(row, k, bool(v))
    row.updated_by = by[:200]
    row.updated_at = datetime.utcnow()

# Module-level state — mutated in place; callers MUST use is_emergency_stop()
# instead of importing the raw name to get the live value.
_EMERGENCY_STOP: bool = False
_DRY_RUN: bool = False
_AI_AUTONOMY_PAUSED: bool = False

# Legacy name aliases kept for backward-compat with any direct assignments
EMERGENCY_STOP = False
DRY_RUN = False


def is_emergency_stop() -> bool:
    """Live getter — always reflects the current state."""
    return _EMERGENCY_STOP


def is_dry_run() -> bool:
    """Live getter — always reflects the current state."""
    return _DRY_RUN


def is_ai_autonomy_paused() -> bool:
    """
    Live getter for the AI-autonomy freeze (PLAN.md §5.3/§7). When True, the
    AI-managed task/wallet engine must not make any autonomous change —
    pausing tasks, adjusting wallet settings, reprioritizing the queue, etc.
    Independent of the main kill switch: this only affects AI decisions, not
    the agent's normal task execution.
    """
    return _AI_AUTONOMY_PAUSED


def set_ai_autonomy_paused(value: bool) -> None:
    global _AI_AUTONOMY_PAUSED
    _AI_AUTONOMY_PAUSED = value


def set_dry_run(value: bool) -> None:
    global _DRY_RUN, DRY_RUN
    _DRY_RUN = value
    DRY_RUN = value


async def activate_kill_switch(db: AsyncSession, reason: str = "manual"):
    """Emergency stop. Persisted: it stays active across a restart until explicitly cleared."""
    global _EMERGENCY_STOP, EMERGENCY_STOP
    _EMERGENCY_STOP = True
    EMERGENCY_STOP = True
    status = await db.get(AgentStatus, 1)
    if status:
        status.status = "stopped"
    await _persist(db, reason, emergency_stop=True)
    await db.commit()


async def deactivate_kill_switch(db: AsyncSession, by: str = "manual clear"):
    global _EMERGENCY_STOP, EMERGENCY_STOP
    _EMERGENCY_STOP = False
    EMERGENCY_STOP = False
    status = await db.get(AgentStatus, 1)
    if status:
        status.status = "running"
    await _persist(db, by, emergency_stop=False)
    await db.commit()


async def set_dry_run_persistent(db: AsyncSession, value: bool, by: str = "manual") -> None:
    """Set the global dry-run flag AND persist it (use this instead of set_dry_run in handlers)."""
    set_dry_run(value)
    await _persist(db, by, dry_run=value)
    await db.commit()


async def load_kill_switch_state(env_dry_run: bool = False) -> None:
    """Call once at startup, after init_db() and BEFORE the scheduler/agent loop start.

    Emergency stop: restored exactly as saved.
    Dry-run: ON if it was saved ON **or** DRY_RUN_MODE=true in the environment. The env value
    can therefore only force dry-run on at boot, never off; to run live permanently set
    DRY_RUN_MODE=false and switch dry-run off in the dashboard (that choice is then saved).
    """
    try:
        async with async_session() as db:
            row = await db.get(KillSwitchState, 1)
            emergency = bool(row and row.emergency_stop)
            dry = bool(row and row.dry_run) or bool(env_dry_run)
            global _EMERGENCY_STOP, EMERGENCY_STOP
            _EMERGENCY_STOP = emergency
            EMERGENCY_STOP = emergency
            set_dry_run(dry)
            if dry and not (row and row.dry_run):
                await _persist(db, "env DRY_RUN_MODE", dry_run=True)
                await db.commit()
            if emergency:
                logger.warning("EMERGENCY STOP is ACTIVE (restored from DB). Nothing will run until it is "
                               "cleared (dashboard System panel or /agent_resume_all).")
            if dry:
                logger.warning("DRY-RUN is ON (%s). No transactions will be broadcast.",
                               "saved state" if (row and row.dry_run) else "DRY_RUN_MODE env")
    except Exception as e:
        # Fail SAFE: if the state cannot be read, do not go live.
        logger.error("load_kill_switch_state failed (%s): starting in emergency stop + dry-run", e)
        _EMERGENCY_STOP = True
        EMERGENCY_STOP = True
        set_dry_run(True)
