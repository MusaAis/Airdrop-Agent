import logging
from backend.agent import start_agent, stop_agent, worker_pool
from backend.core.kill_switch import activate_kill_switch, deactivate_kill_switch
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.agent_extras")


async def handle_agent_start(user_id, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if worker_pool.running:
        return "⚠️ Agent is already running."
    start_agent()
    return "▶️ Agent started."


async def handle_agent_stop(user_id, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    stop_agent()
    return "🛑 Agent stop initiated. Current tasks will finish gracefully."


async def handle_agent_pause_all(user_id, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    await activate_kill_switch(db, reason="manual pause_all")
    return "⏸️ All farming paused. Use /agent_resume_all to resume."


async def handle_agent_resume_all(user_id, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    await deactivate_kill_switch(db)
    return "▶️ Farming resumed. Queue will refill on next cycle (30s)."


async def handle_agent_workers(user_id, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    lines = []
    for i, s in enumerate(worker_pool.slots):
        if s:
            w = s.get("wallet")
            tc = s.get("task_config")
            proj = s.get("project")
            lines.append(
                f"Slot {i}: 🟢 wallet#{w.id} | {tc.task_type} | {proj.name}"
            )
        else:
            lines.append(f"Slot {i}: ⚪ idle")
    status = "🟢 running" if worker_pool.running else "🔴 stopped"
    queued = len(worker_pool.queue)
    header = f"Agent: {status} | Queue: {queued} tasks\n"
    return header + "\n".join(lines)


async def handle_agent_queue(user_id, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    queue = worker_pool.queue
    if not queue:
        return "📭 Queue is empty."
    lines = []
    for i, q in enumerate(queue[:20]):
        w = q.get("wallet")
        tc = q.get("task_config")
        proj = q.get("project")
        lines.append(f"{i+1}. wallet#{w.id} | {proj.name} | {tc.task_type} | prio {q['priority']}")
    footer = f"\n... and {len(queue)-20} more" if len(queue) > 20 else ""
    return "\n".join(lines) + footer
