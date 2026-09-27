from typing import Optional
from backend.models import AgentStatus
from sqlalchemy.ext.asyncio import AsyncSession

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
    global _EMERGENCY_STOP, EMERGENCY_STOP
    _EMERGENCY_STOP = True
    EMERGENCY_STOP = True
    status = await db.get(AgentStatus, 1)
    if status:
        status.status = "stopped"
        await db.commit()


async def deactivate_kill_switch(db: AsyncSession):
    global _EMERGENCY_STOP, EMERGENCY_STOP
    _EMERGENCY_STOP = False
    EMERGENCY_STOP = False
    status = await db.get(AgentStatus, 1)
    if status:
        status.status = "running"
        await db.commit()
