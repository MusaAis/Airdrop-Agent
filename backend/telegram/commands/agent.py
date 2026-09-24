from sqlalchemy.ext.asyncio import AsyncSession
from backend.agent import worker_pool
from backend.core.kill_switch import is_emergency_stop
from backend.telegram.whitelist import is_whitelisted
from backend.wallet.hd_generator import set_master_seed, decrypt_seed, get_master_seed
from backend.database import async_session
from backend.models import AgentSecret
from sqlalchemy import select
from backend.config import MASTER_PASSWORD

async def handle_agent_status(user_id: int, db: AsyncSession):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    running = worker_pool.running
    slots = sum(1 for s in worker_pool.slots if s is not None)
    em = "🔴 EMERGENCY STOP" if is_emergency_stop() else "🟢 Normal"
    seed_loaded = "yes" if get_master_seed() else "no"
    return f"Agent: {'Running' if running else 'Stopped'}\nWorker slots: {slots}/{worker_pool.max_slots}\nSeed loaded: {seed_loaded}\n{em}"

async def handle_agent_stop(user_id: int, db: AsyncSession):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.agent import stop_agent
    stop_agent()
    return "🛑 Agent stop initiated."

async def handle_agent_unlock(user_id: int, password: str, db: AsyncSession):
    """Unlock the stored seed with the master password."""
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    async with async_session() as db:
        entry = (await db.execute(select(AgentSecret).where(AgentSecret.key == 'master_mnemonic'))).scalar_one_or_none()
        if not entry:
            return "❌ No stored seed. Use /agent_set_seed first."
        try:
            mnemonic = decrypt_seed(entry.value, password)
            set_master_seed(mnemonic)
            return "✅ Seed unlocked and ready."
        except Exception:
            return "❌ Wrong master password or corrupted seed."

async def handle_agent_kill(user_id: int, db):
    """Emergency kill switch — stops the agent loop and marks DB status stopped."""
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.core.kill_switch import activate_kill_switch
    from backend.agent import stop_agent

    # Drain the in-memory queue BEFORE stopping. activate_kill_switch() only
    # stops NEW items from being added (via periodic_fill's is_emergency_stop()
    # check); it doesn't touch what's already queued. Without this, a worker
    # slot freed up during stop_agent()'s graceful drain could still pop the
    # next already-queued item and execute a real transaction, even though the
    # user was told "Agent halted" immediately. Anything already mid-execution
    # in a slot right now will still finish that one transaction — a broadcast
    # tx can't be un-sent — but nothing further will be picked up after it.
    queued_count = len(worker_pool.queue)
    async with worker_pool.lock:
        worker_pool.queue.clear()
        worker_pool.active_task_ids.clear()

    await activate_kill_switch(db, reason=f"manual kill by user {user_id}")
    stop_agent()
    return (
        f"🔴 EMERGENCY STOP activated. Cleared {queued_count} queued task(s). "
        f"Agent halted (any transaction already mid-flight in a worker slot will "
        f"still finish — it cannot be un-broadcast). Use /agent_start to resume."
    )

async def handle_agent_dryrun_on(user_id: int, db):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.core.kill_switch import set_dry_run
    set_dry_run(True)
    return "🟡 Dry-run mode ON — agent will simulate but not submit transactions."

async def handle_agent_dryrun_off(user_id: int, db):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.core.kill_switch import set_dry_run
    set_dry_run(False)
    return "🟢 Dry-run mode OFF — agent will submit live transactions."

async def handle_agent_restart(user_id: int, db):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.agent import stop_agent, start_agent
    import asyncio; stop_agent(); await asyncio.sleep(2); start_agent()
    return "♻️ Agent restarted."

async def handle_agent_schedule_preview(user_id: int, db):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from sqlalchemy import select as _s; from backend.models import TaskSchedule, TaskConfig
    items = (await db.execute(_s(TaskSchedule).where(TaskSchedule.enabled==True).order_by(TaskSchedule.next_run_at.asc()).limit(20))).scalars().all()
    if not items: return "No upcoming tasks."
    lines = ["Next 20 scheduled tasks:"]
    for s in items:
        task = await db.get(TaskConfig, s.task_config_id)
        lines.append(f"  {s.next_run_at.strftime('%H:%M') if s.next_run_at else '?'} W{s.wallet_id} — {task.task_type if task else '?'}")
    return "\n".join(lines)
