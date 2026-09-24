import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.telegram.whitelist import is_whitelisted

async def handle_discovery_run(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    # Previously this called backend.discovery.scheduler.run_discovery_all(),
    # which is wired to 4 legacy stub functions that always return [] — so
    # this command reported "Discovery scan triggered" but silently did
    # nothing, every time. The real, working aggregator is run_all_scrapers()
    # in backend.discovery.scraper — it's what core/scheduler.py's automatic
    # 6-hour job actually calls. Wiring this command to the same function
    # means manual and scheduled discovery now run identical, real code.
    from backend.discovery.scraper import run_all_scrapers
    from backend.discovery.processor import process_discovery_results
    results = await run_all_scrapers()
    await process_discovery_results(results)
    return f"✅ Discovery scan complete — {len(results)} raw result(s) found across all sources. Check /ai_log or the AI Log dashboard page for validation results."

async def handle_discovery_sources(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    # List available sources (hardcoded for now, could be in DB)
    return "Available sources: defillama, cryptorank, airdrops_io, l2beat, twitter, rootdata"

async def handle_discovery_enable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: discovery.enable <source>"
    # Store enabled sources in a config table (not yet implemented), so just acknowledge
    return f"Source '{args[0]}' enabled (not persistent across restarts)."

async def handle_discovery_disable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: discovery.disable <source>"
    return f"Source '{args[0]}' disabled (not persistent across restarts)."

async def handle_discovery_pending(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    # Pending projects would be stored in a table (not implemented), so none
    return "No pending discoveries. Run discovery.run to scan."

async def handle_discovery_set_interval(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: discovery.set_interval <hours>"
    hours = int(args[0])
    # Previously this called discovery/scheduler.py's start_discovery_scheduler(),
    # which spins up a SEPARATE AsyncIOScheduler instance running the old,
    # stub-wired discovery job — i.e. a second scheduler that does nothing,
    # running alongside the real one in core/scheduler.py that does the
    # actual work. Now it reschedules the real, already-running "discovery"
    # job in place via the shared scheduler instance.
    from backend.core.scheduler import get_scheduler
    from apscheduler.triggers.interval import IntervalTrigger
    sched = get_scheduler()
    sched.reschedule_job("discovery", trigger=IntervalTrigger(hours=hours))
    return f"Discovery interval set to {hours} hours."
