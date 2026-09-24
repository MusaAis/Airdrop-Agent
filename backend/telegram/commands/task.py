import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.projects.manager import list_task_configs, get_task_config, update_task_config
from backend.agent import worker_pool
from backend.wallet.manager import get_wallet
from backend.chains.manager import get_chain
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.task")

async def handle_task_list(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    proj_id = int(args[0]) if args else None
    tasks = await list_task_configs(db, project_id=proj_id)
    if not tasks: return "No tasks."
    return "\n".join(f"{t.id}: {t.task_type} (proj:{t.project_id}) enabled:{t.enabled}" for t in tasks)

async def handle_task_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: task.status <id>"
    t = await get_task_config(db, int(args[0]))
    if not t: return "Task not found."
    return f"Task {t.id}: {t.task_type} enabled:{t.enabled} freq:{t.frequency_mins}m"

async def handle_task_enable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: task.enable <id>"
    await update_task_config(db, int(args[0]), enabled=True)
    return "✅ Task enabled."

async def handle_task_pause(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: task.pause <id>"
    if confirmation is None: return "⚠️ Confirm pause task? Reply 'confirm'"
    await update_task_config(db, int(args[0]), enabled=False)
    return "⏸ Task paused."

async def handle_task_trigger(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: task.trigger <task_id> <wallet_id>"
    tid = int(args[0])
    wid = int(args[1]) if len(args) > 1 else None
    task = await get_task_config(db, tid)
    if not task: return "Task not found."
    # Select a wallet
    if wid:
        wallet = await get_wallet(db, wid)
        if not wallet: return "Wallet not found."
        wallets = [wallet]
    else:
        # Pick a random active wallet
        from backend.wallet.manager import list_wallets
        all_wallets = await list_wallets(db, status_filter="active")
        if not all_wallets: return "No active wallets."
        import random
        wallets = [random.choice(all_wallets)]
    # Get chain
    chain = await get_chain(db, task.chain_id)
    if not chain: return "Chain not found."
    # Get project (needed for queue)
    from backend.projects.manager import get_project
    project = await get_project(db, task.project_id)
    if not project: return "Project not found."
    # Enqueue the task
    items = []
    for wallet in wallets:
        items.append({
            "wallet": wallet,
            "task_config": task,
            "project": project,
            "chain": chain,
            "priority": project.priority
        })
    await worker_pool.enqueue(items)
    return f"✅ Triggered task {tid} for {len(wallets)} wallet(s)."

async def handle_task_dry_run(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    return "Dry run will be executed during next agent cycle with DRY_RUN_MODE=true in .env."

async def handle_task_deps(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: task.deps <id>"
    t = await get_task_config(db, int(args[0]))
    if not t: return "Task not found."
    if not t.dependency_task_ids: return f"Task {t.id} ({t.task_type}) has no dependencies."
    lines = [f"Task {t.id} ({t.task_type}) depends on:"]
    for dep_id in t.dependency_task_ids:
        dep = await get_task_config(db, dep_id)
        lines.append(f"  → {dep_id}: {dep.task_type if dep else 'NOT FOUND'}")
    return "\n".join(lines)

async def handle_task_set_priority(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 2: return "Usage: task.set_priority <id> <1-10>"
    from sqlalchemy import select as _s; from backend.models import TaskSchedule
    for s in (await db.execute(_s(TaskSchedule).where(TaskSchedule.task_config_id==int(args[0])))).scalars().all():
        s.priority = max(1, min(10, int(args[1])))
    await db.commit(); return f"✅ Priority set to {args[1]} for task {args[0]}."

async def handle_task_trigger_all(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: task.trigger_all <project_id>"
    from backend.projects.manager import get_project
    from backend.wallet.manager import list_wallets
    from backend.chains.manager import get_chain
    from backend.agent import worker_pool
    import random
    pid = int(args[0]); project = await get_project(db, pid)
    if not project: return "Project not found."
    tasks = await list_task_configs(db, project_id=pid)
    wallets = await list_wallets(db, status_filter="active")
    if not wallets: return "No active wallets."
    items = []
    for t in tasks:
        chain = await get_chain(db, t.chain_id)
        if chain: items.append({"wallet": random.choice(wallets), "task_config": t, "project": project, "chain": chain, "priority": project.priority})
    await worker_pool.enqueue(items)
    return f"✅ Triggered {len(items)} tasks for '{project.name}'."

async def handle_task_template(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    templates = {"defi-basic": ["swap","bridge","stake"], "defi-advanced": ["swap","bridge","stake","provide_liquidity","claim_rewards"], "nft": ["mint_nft","transfer_nft"], "governance": ["vote","delegate"], "lending": ["deposit","withdraw","borrow","repay"]}
    lines = ["Available task templates:"]
    for name, tasks in templates.items():
        lines.append(f"  {name}: {', '.join(tasks)}")
    return "\n".join(lines)
