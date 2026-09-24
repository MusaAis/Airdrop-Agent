"""
discovery/scraper.py — thin aggregator that delegates to the real
per-source scrapers in discovery/sources/*.  The old stub functions
(scrape_defillama etc.) are replaced by run_all_scrapers(), which is
what core/scheduler.py now calls.
"""
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

logger = logging.getLogger("airdrop.discovery.scraper")


async def fetch_with_proxy(url: str, proxy_url: Optional[str] = None) -> str:
    proxies = {"http://": proxy_url, "https://": proxy_url} if proxy_url else None
    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def run_all_scrapers() -> List[Dict]:
    """Aggregate results from all real discovery sources."""
    from backend.discovery.sources import (
        defillama, cryptorank, airdrops_io, twitter, rootdata, l2beat
    )
    raw = await asyncio.gather(
        defillama.scrape(),
        cryptorank.scrape(),
        airdrops_io.scrape(),
        twitter.scrape(),
        rootdata.scrape(),
        l2beat.scrape(),
        return_exceptions=True,
    )
    results = [item for batch in raw if isinstance(batch, list) for item in batch]
    logger.info(f"run_all_scrapers: {len(results)} total results across all sources")
    return results


# Legacy stub aliases — kept so any import that still uses these names
# doesn't blow up with ImportError (they now return [] just like before,
# but run_all_scrapers is the real entry point).
async def scrape_defillama(): return []
async def scrape_cryptorank(): return []
async def scrape_airdrops_io(): return []
async def scrape_twitter(): return []
async def scrape_rootdata(): return []
async def scrape_l2beat(): return []
