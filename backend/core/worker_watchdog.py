import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from backend.database import async_session
from backend.models import ActiveTask

logger = logging.getLogger("airdrop.watchdog")


async def watch_frozen_slots(worker_pool, check_interval_secs: int = 60) -> None:
    """Periodically detect and cancel frozen worker slots."""
    while worker_pool.running:
        try:
            await _check_and_recover(worker_pool)
        except Exception as e:
            logger.error(f"Watchdog error: {e}")
        await asyncio.sleep(check_interval_secs)


async def _check_and_recover(worker_pool) -> None:
    now = datetime.now(timezone.utc)

    async with async_session() as db:
        result = await db.execute(select(ActiveTask))
        active_tasks = result.scalars().all()

        for task in active_tasks:
            if not task.timeout_at:
                continue
            if now <= task.timeout_at:
                continue

            age_mins = (now - task.started_at).total_seconds() / 60
            logger.warning(
                f"Frozen task: wallet={task.wallet_id} "
                f"chain={task.chain_id} slot={task.worker_slot} "
                f"age={age_mins:.1f}min"
            )

            # Release nonce lock
            from backend.core.nonce_manager import release_nonce
            try:
                await release_nonce(db, task.wallet_id, task.chain_id, increment=False)
            except Exception as e:
                logger.error(f"Nonce release failed: {e}")

            # Remove from active_tasks
            await db.delete(task)
            await db.commit()

            # Cancel and respawn the frozen asyncio slot
            slot_id = task.worker_slot
            if slot_id is not None and hasattr(worker_pool, "slot_tasks"):
                slot_task = worker_pool.slot_tasks.get(slot_id)
                if slot_task and not slot_task.done():
                    slot_task.cancel()
                    logger.info(f"Cancelled frozen slot {slot_id}, respawning")
                    try:
                        new_task = asyncio.create_task(worker_pool._worker(slot_id))
                        worker_pool.slot_tasks[slot_id] = new_task
                    except Exception as e:
                        logger.error(f"Slot respawn failed: {e}")
