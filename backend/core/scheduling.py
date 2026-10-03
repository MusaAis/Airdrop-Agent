"""
Human-like pacing (review item H4).

Before this module, frequency_mins, the persona's sleep range and start offset were stored and
shown in the UI but never enforced: a wallet that finished a task was eligible again on the very
next 30 s queue cycle and ran until its daily target was hit, a burst no person produces.

Rules now enforced in queue_manager._get_project_candidates:
  * per (wallet, task): TaskSchedule.next_run_at. After an attempt the task is not due again until
        success  -> frequency_mins x U(0.8, 1.4)
        failed   -> ~10 min x U(0.8, 1.5)   (timeouts and config errors count as failed)
        skipped  -> U(3, 8) min             (gas spike, low gas, paused contract, memory pressure)
  * per wallet: Wallet.next_available_at = now + U(sleep_min_mins, sleep_max_mins) after any attempt,
        so a wallet never does two things back to back.
  * per wallet per day: no task until the active window opened + a deterministic personal offset
        in [0, start_offset_max_mins] (see behavior_randomizer.has_started_for_the_day).
  * one task per wallet per queue fill (a wallet with tasks on two chains used to get both at once).
Dry-run ("simulated") results never touch the schedule.
"""
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskSchedule, Wallet
from backend.wallet.manager import get_wallet_settings
from backend.wallet.behavior_randomizer import get_sleep_seconds

logger = logging.getLogger("airdrop.scheduling")

DEFAULT_FREQUENCY_MINS = 120
SUCCESS_JITTER = (0.8, 1.4)
FAILURE_BACKOFF_MINS = 10
FAILURE_JITTER = (0.8, 1.5)
SKIP_BACKOFF_MINS = (3.0, 8.0)
OUTCOMES = ("success", "failed", "skipped")


def utcnow_naive() -> datetime:
    """The DateTime columns are naive UTC; keep every comparison in that one convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def task_delay_minutes(outcome: str, frequency_mins: Optional[int], rng=random) -> float:
    """Minutes until the same (wallet, task) may run again."""
    if outcome == "success":
        freq = max(1, int(frequency_mins or DEFAULT_FREQUENCY_MINS))
        return freq * rng.uniform(*SUCCESS_JITTER)
    if outcome == "failed":
        return FAILURE_BACKOFF_MINS * rng.uniform(*FAILURE_JITTER)
    if outcome == "skipped":
        return rng.uniform(*SKIP_BACKOFF_MINS)
    raise ValueError(f"unknown outcome {outcome!r}")


async def record_attempt(db: AsyncSession, wallet_id: int, task_config, outcome: str,
                         now: Optional[datetime] = None) -> None:
    """Update TaskSchedule (upsert) and Wallet.next_available_at after a real attempt.
    Never raises: pacing bookkeeping must not break outcome handling."""
    if outcome not in OUTCOMES:
        return
    try:
        now = now or utcnow_naive()
        settings = await get_wallet_settings(db, wallet_id)
        next_run = now + timedelta(minutes=task_delay_minutes(outcome, task_config.frequency_mins))
        row = (await db.execute(
            select(TaskSchedule).where(TaskSchedule.wallet_id == wallet_id,
                                       TaskSchedule.task_config_id == task_config.id)
        )).scalar_one_or_none()
        if row is None:
            db.add(TaskSchedule(wallet_id=wallet_id, task_config_id=task_config.id,
                                next_run_at=next_run, last_run_at=now, enabled=True, priority=5))
        else:
            row.next_run_at = next_run
            row.last_run_at = now
        wallet = await db.get(Wallet, wallet_id)
        if wallet is not None:
            wallet.next_available_at = now + timedelta(seconds=get_sleep_seconds(settings))
            if outcome == "success":
                wallet.last_active = now
        await db.commit()
    except Exception as e:
        logger.warning("record_attempt failed for wallet=%s task=%s: %s", wallet_id,
                       getattr(task_config, "id", "?"), e)
        try:
            await db.rollback()
        except Exception:
            pass


async def load_schedule_map(db: AsyncSession, task_config_ids: list) -> dict:
    """{(wallet_id, task_config_id): next_run_at} for the given task configs, in ONE query."""
    if not task_config_ids:
        return {}
    rows = (await db.execute(
        select(TaskSchedule).where(TaskSchedule.task_config_id.in_(task_config_ids))
    )).scalars().all()
    return {(r.wallet_id, r.task_config_id): r.next_run_at for r in rows}
