import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc
from backend.models import TaskSchedule, TaskConfig, Wallet, Project
from backend.telegram.whitelist import is_whitelisted

async def handle_schedule_next(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    n = int(args[0]) if args else 10
    items = (await db.execute(
        select(TaskSchedule).order_by(asc(TaskSchedule.next_run_at)).limit(n)
    )).scalars().all()
    if not items: return "No scheduled tasks."
    lines = []
    for s in items:
        task = await db.get(TaskConfig, s.task_config_id)
        wallet = await db.get(Wallet, s.wallet_id) if s.wallet_id else None
        lines.append(f"Wallet {wallet.id if wallet else '?'} – {task.task_type if task else '?'} at {s.next_run_at}")
    return "\n".join(lines)

async def handle_schedule_pause(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: schedule.pause <wallet_id>"
    wid = int(args[0])
    # Set all schedules for this wallet to enabled=False
    await db.execute(
        select(TaskSchedule).where(TaskSchedule.wallet_id == wid)
    )
    schedules = (await db.execute(select(TaskSchedule).where(TaskSchedule.wallet_id == wid))).scalars().all()
    for s in schedules:
        s.enabled = False
    await db.commit()
    return f"Paused {len(schedules)} schedules for wallet {wid}."

async def handle_schedule_resume(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: schedule.resume <wallet_id>"
    wid = int(args[0])
    schedules = (await db.execute(select(TaskSchedule).where(TaskSchedule.wallet_id == wid))).scalars().all()
    for s in schedules:
        s.enabled = True
    await db.commit()
    return f"Resumed {len(schedules)} schedules for wallet {wid}."

async def handle_schedule_set(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 2: return "Usage: schedule.set <task_id> <interval_mins>"
    from backend.models import TaskConfig
    task = await db.get(TaskConfig, int(args[0]))
    if not task: return "Task not found."
    task.frequency_mins = int(args[1]); await db.commit()
    return f"✅ Task {args[0]} interval set to {args[1]} mins."

async def handle_schedule_set_window(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 3: return "Usage: schedule.set_window <wallet_id> <start_hour> <end_hour>"
    from sqlalchemy import select as _s; from backend.models import WalletSettings
    wid = int(args[0])
    ws = (await db.execute(_s(WalletSettings).where(WalletSettings.wallet_id==wid))).scalar_one_or_none()
    if not ws: ws = WalletSettings(wallet_id=wid); db.add(ws)
    ws.active_hour_start = int(args[1]); ws.active_hour_end = int(args[2])
    await db.commit(); return f"✅ Active window for wallet {wid}: {args[1]}:00–{args[2]}:00 UTC."
