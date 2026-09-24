"""
RootData discovery — VC-backed early-stage Web3 projects.

RootData is a React SPA. Static HTML scraping returns zero project cards
because all data is loaded via client-side JavaScript calls to their API.

The old scraper used BeautifulSoup with class selectors like "project-item"
and "card" — these don't exist in the initial HTML payload.

This version uses RootData's internal API endpoints that their frontend
calls. These are undocumented but stable, and return JSON directly.

If the API becomes unavailable, the scraper logs a warning and returns []
gracefully so other sources still run.

Focus: projects that raised funding in the last 6 months with no token yet.
"""

import httpx
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict

logger = logging.getLogger("airdrop.discovery.rootdata")

# RootData internal API endpoints
# The /projects endpoint returns a list with funding info and token status
SEARCH_URL = "https://api.rootdata.com/open/ser_inv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.rootdata.com",
    "Referer": "https://www.rootdata.com/",
}

MAX_RESULTS = 20
# Only look at projects that raised funding in the last 6 months
MAX_FUNDING_AGE_DAYS = 180


async def scrape() -> List[Dict]:
    results = []
    try:
        async with httpx.AsyncClient(
            timeout=30, headers=HEADERS, follow_redirects=True
        ) as client:
            # Search for recently funded projects with no token
            payload = {
                "query": "",
                "page": 1,
                "page_size": 50,
                "sort": "newest",  # most recent first
            }
            resp = await client.post(SEARCH_URL, json=payload)

            if resp.status_code == 404:
                logger.warning(
                    "RootData API returned 404 — endpoint may have changed. "
                    "Returning empty results."
                )
                return []
            if resp.status_code == 403:
                logger.warning("RootData API returned 403 — may require auth now. Skipping.")
                return []
            if resp.status_code != 200:
                logger.warning("RootData API returned HTTP %d", resp.status_code)
                return []

            data = resp.json()
            items = data.get("data") or data.get("result") or data.get("projects") or []
            if not isinstance(items, list):
                logger.warning("RootData: unexpected response shape: %s", list(data.keys()))
                return []

            cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_FUNDING_AGE_DAYS)
            seen: set = set()

            for item in items:
                name = (item.get("name") or item.get("project_name") or "").strip()
                if not name or name.lower() in seen:
                    continue

                # Skip if token already exists
                token = item.get("token_symbol") or item.get("symbol")
                if token and token not in ("-", "N/A", ""):
                    continue

                # Check funding date — skip if too old
                funded_raw = (
                    item.get("latest_funding_date")
                    or item.get("funding_date")
                    or item.get("created_at")
                )
                if funded_raw:
                    try:
                        funded_dt = datetime.fromisoformat(
                            str(funded_raw).replace("Z", "+00:00")
                        )
                        if funded_dt.tzinfo is None:
                            funded_dt = funded_dt.replace(tzinfo=timezone.utc)
                        if funded_dt < cutoff:
                            continue
                    except Exception:
                        pass  # can't parse date, keep the project

                funding_amount = item.get("total_funding") or item.get("funding_amount")
                investors = item.get("investors") or item.get("vcs") or []
                if isinstance(investors, list):
                    investor_names = [
                        (v.get("name") or v) if isinstance(v, dict) else str(v)
                        for v in investors[:5]
                    ]
                else:
                    investor_names = []

                website = item.get("website") or item.get("url")
                twitter = item.get("twitter") or item.get("twitter_url")

                desc_parts = [item.get("description") or item.get("intro") or ""]
                if investor_names:
                    desc_parts.append(f"Investors: {', '.join(investor_names)}")
                if funding_amount:
                    desc_parts.append(f"Raised: {funding_amount}")

                seen.add(name.lower())
                results.append({
                    "name": name,
                    "description": " | ".join(filter(None, desc_parts))[:400],
                    "chain": item.get("blockchain") or item.get("chain") or "Unknown",
                    "website": website,
                    "twitter": twitter,
                    "source": "rootdata",
                    "token_symbol": None,
                    "vc_backers": investor_names,
                    "funding_amount": str(funding_amount) if funding_amount else None,
                    "listed_at": funded_raw,  # for freshness filter in processor
                })

                if len(results) >= MAX_RESULTS:
                    break

    except Exception as e:
        logger.error("RootData scrape error: %s", e)

    logger.info("RootData: %d VC-backed no-token projects found", len(results))
    return results
