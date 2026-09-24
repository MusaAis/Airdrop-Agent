"""
DEPRECATED — not used anywhere as of this fix.

This was the original discovery scheduler, wired to scrape_defillama() etc.
in discovery/scraper.py — which are now no-op legacy stub aliases that always
return []. The real, working discovery scan runs via core/scheduler.py's
"discovery" job (every 6h), which calls discovery.scraper.run_all_scrapers()
— the actual aggregator hitting discovery/sources/*.py.

Both Telegram commands that used to import from this file
(discovery.run, discovery.set_interval) have been repointed at the real
scheduler. This file is kept only so nothing else importing it unexpectedly
breaks; do not add new functionality here — add it to core/scheduler.py.
"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.discovery.processor import process_discovery_results
from backend.discovery.scraper import scrape_defillama, scrape_cryptorank, scrape_airdrops_io, scrape_l2beat

logger = logging.getLogger("airdrop.discovery")

scheduler = AsyncIOScheduler()

async def run_discovery_all():
    logger.info("Running discovery scan...")
    results = []
    # gather from all sources
    tasks = [
        scrape_defillama(),
        scrape_cryptorank(),
        scrape_airdrops_io(),
        scrape_l2beat(),
    ]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    for res in gathered:
        if isinstance(res, list):
            results.extend(res)
    await process_discovery_results(results)

def start_discovery_scheduler(interval_hours: int = 6):
    scheduler.add_job(run_discovery_all, 'interval', hours=interval_hours, id='discovery')
    scheduler.start()
    logger.info(f"Discovery scheduler started, every {interval_hours}h")
