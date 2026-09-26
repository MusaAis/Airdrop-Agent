import logging
from backend.telegram.whitelist import is_whitelisted
from backend.reports.server import get_server_status

logger = logging.getLogger("airdrop.tg.system")

# In-memory maintenance window
_maintenance_window = {"active": False, "start": None, "end": None}


async def handle_system_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    s = get_server_status()
    em = "🔴 EMERGENCY STOP" if s.get("emergency_stop") else "🟢 Normal"
    maint = " | 🔧 Maintenance ON" if _maintenance_window["active"] else ""
    return (
        f"⚙️ System Status\n"
        f"RAM: {s['ram_percent']}% ({s['ram_used_gb']}/{s['ram_total_gb']} GB)\n"
        f"CPU: {s['cpu_percent']}%\n"
        f"Disk: {s['disk_percent']}% used ({s['disk_free_gb']} GB free)\n"
        f"Workers: {s['worker_slots_active']}/{s['worker_slots_max']}\n"
        f"Agent: {'🟢 running' if s['agent_running'] else '🔴 stopped'}\n"
        f"Status: {em}{maint}"
    )


async def handle_system_test_rpc(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import Chain
    from sqlalchemy import select
    from backend.chains.rpc_checker import check_chain_rpcs
    try:
        chain_id = int(args[0]) if args else None
        query = select(Chain).where(Chain.enabled == True)
        if chain_id:
            query = query.where(Chain.id == chain_id)
        chains = (await db.execute(query)).scalars().all()
        if not chains:
            return "No enabled chains found."
        lines = []
        for chain in chains:
            try:
                result = await check_chain_rpcs(chain)
                lines.append(f"✅ {chain.name}: {result}")
            except Exception as e:
                lines.append(f"❌ {chain.name}: {e}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ RPC test error: {e}"


async def handle_system_maintenance(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 2:
        return "Usage: /system_maintenance <start_hour> <end_hour> (UTC, 0-23)"
    try:
        start = int(args[0])
        end = int(args[1])
        if not (0 <= start <= 23 and 0 <= end <= 23):
            return "Hours must be 0-23 (UTC)."
        _maintenance_window.update({"active": True, "start": start, "end": end})
        return f"🔧 Maintenance window set: {start:02d}:00–{end:02d}:00 UTC. Tasks will pause during this window."
    except ValueError:
        return "Invalid hours. Usage: /system_maintenance <start_hour> <end_hour>"


async def handle_system_maintenance_off(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    _maintenance_window.update({"active": False, "start": None, "end": None})
    return "✅ Maintenance window cancelled. Normal operation resumed."


async def handle_system_log_archive(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    try:
        from backend.maintenance.log_archiver import run_all_maintenance
        result = await run_all_maintenance()
        return (
            f"✅ Maintenance complete.\n"
            f"Logs archived: {result['logs_archived']}\n"
            f"RPC logs purged: {result['rpc_logs_purged']}"
        )
    except Exception as e:
        return f"❌ Archive failed: {e}"


async def handle_system_version(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import AgentStatus
    status = await db.get(AgentStatus, 1)
    uptime = "Unknown"
    if status and status.uptime_start:
        from datetime import datetime, timezone
        uptime_start = status.uptime_start
        if uptime_start.tzinfo is None:
            uptime_start = uptime_start.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - uptime_start
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m = rem // 60
        uptime = f"{h}h {m}m"
    return (
        f"🤖 Airdrop Agent v1.0\n"
        f"Uptime: {uptime}\n"
        f"Status: {'🟢 running' if status and status.status == 'running' else '🔴 stopped'}"
    )
