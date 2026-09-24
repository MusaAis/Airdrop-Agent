import asyncio
import logging
import signal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import async_session
from backend.models import AgentStatus
from backend.core.worker_pool import WorkerPool
from backend.core.queue_manager import fill_queue
from backend.core.memory_guard import check_memory
from backend.core.kill_switch import is_emergency_stop, is_dry_run
from backend.config import MAX_WORKER_SLOTS

logger = logging.getLogger("airdrop.agent")

worker_pool = WorkerPool(max_slots=MAX_WORKER_SLOTS)
agent_task = None

async def agent_loop():
    """Main agent entry point. Runs forever until stopped."""
    global worker_pool
    logger.info("Agent loop started")

    # Initialize agent status in DB
    async with async_session() as db:
        status = await db.get(AgentStatus, 1)
        if not status:
            status = AgentStatus(id=1)
            db.add(status)
        status.status = "running"
        status.uptime_start = datetime.now(timezone.utc)
        status.worker_slots_max = MAX_WORKER_SLOTS
        await db.commit()

    await worker_pool.start()

    # Schedule periodic queue fill every 30 seconds
    async def periodic_fill():
        while worker_pool.running:
            # Use getters — not the imported snapshot — so kill switch works
            if not is_emergency_stop() and not is_dry_run():
                try:
                    await fill_queue(worker_pool)
                    from backend.core.tx_monitor import monitor_pending_transactions
                    await monitor_pending_transactions()
                except Exception as e:
                    logger.error(f"Queue fill error: {e}")
            await asyncio.sleep(30)

    fill_task = asyncio.create_task(periodic_fill())
    from backend.core.worker_watchdog import watch_frozen_slots
    watchdog_task = asyncio.create_task(watch_frozen_slots(worker_pool))

    # Heartbeat update every 60 seconds
    async def heartbeat():
        while worker_pool.running:
            async with async_session() as db:
                status = await db.get(AgentStatus, 1)
                if status:
                    status.last_heartbeat = datetime.now(timezone.utc)
                    status.memory_pct = check_memory()
                    status.worker_slots_active = sum(1 for s in worker_pool.slots if s is not None)
                    status.current_tasks = [
                        {"slot": i, "wallet_id": s["wallet"].id if s else None, "task_type": s["task_config"].task_type if s else None}
                        for i, s in enumerate(worker_pool.slots)
                    ]
                    await db.commit()
            await asyncio.sleep(60)

    heartbeat_task = asyncio.create_task(heartbeat())

    # Wait until stopped
    try:
        while worker_pool.running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Agent loop cancelled")
    finally:
        worker_pool.running = False
        fill_task.cancel()
        watchdog_task.cancel()
        heartbeat_task.cancel()
        await worker_pool.stop()
        async with async_session() as db:
            status = await db.get(AgentStatus, 1)
            if status:
                status.status = "stopped"
                await db.commit()
        logger.info("Agent loop stopped")

def start_agent():
    """Start the agent as an asyncio task."""
    global agent_task
    loop = asyncio.get_event_loop()
    agent_task = loop.create_task(agent_loop())
    return agent_task

def stop_agent():
    if agent_task:
        agent_task.cancel()
