"""
CryptoRank airdrop discovery — uses their public API endpoint.

The old scraper used BeautifulSoup on cryptorank.io/airdrops, which is a
JavaScript-rendered React app. Static HTML scraping returns an empty shell —
no project cards, no data. That version always returned 0 results silently.

This version uses CryptoRank's undocumented-but-public API endpoint that
their own frontend calls. No API key required for basic airdrop listing.

Endpoint: https://api.cryptorank.io/v1/airdrops
Returns JSON with airdrop campaigns including name, status, chain, dates.

Guards:
  - status == "ended" or "finished" → skip (already completed)
  - endDate in the past → skip
  - Hard cap MAX_RESULTS
"""

import httpx
import logging
from datetime import datetime, timezone
from typing import List, Dict

logger = logging.getLogger("airdrop.discovery.cryptorank")

# Public API endpoint — no key needed for listing
API_URL = "https://api.cryptorank.io/v1/airdrops"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://cryptorank.io",
    "Referer": "https://cryptorank.io/",
}

MAX_RESULTS = 25
_ENDED_STATUSES = {"ended", "finished", "completed", "closed", "expired"}


def _is_expired(item: dict) -> bool:
    """Return True if the campaign end date is in the past."""
    end_raw = item.get("endDate") or item.get("end_date") or item.get("endAt")
    if not end_raw:
        return False  # no end date — give benefit of the doubt
    try:
        if isinstance(end_raw, str):
            dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
        else:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < datetime.now(timezone.utc)
    except Exception:
        return False


async def scrape() -> List[Dict]:
    results = []
    try:
        async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
            resp = await client.get(API_URL, params={"limit": 100, "offset": 0})

            if resp.status_code == 404:
                # API endpoint moved — log and return empty so other sources still run
                logger.warning("CryptoRank API endpoint returned 404 — may have changed")
                return []
            if resp.status_code != 200:
                logger.warning("CryptoRank API returned HTTP %d", resp.status_code)
                return []

            data = resp.json()
            # API returns either a list or {"data": [...]}
            items = data if isinstance(data, list) else data.get("data", [])

            seen: set = set()
            for item in items:
                name = (
                    item.get("name")
                    or item.get("project", {}).get("name")
                    or item.get("projectName")
                    or ""
                ).strip()
                if not name or name.lower() in seen:
                    continue

                # Skip ended campaigns
                status = (item.get("status") or "").lower()
                if status in _ENDED_STATUSES:
                    continue
                if _is_expired(item):
                    continue

                chain = (
                    item.get("chain")
                    or item.get("blockchain")
                    or item.get("network")
                    or "Unknown"
                )
                if isinstance(chain, dict):
                    chain = chain.get("name", "Unknown")

                website = item.get("website") or item.get("url") or item.get("projectUrl")
                twitter = item.get("twitter") or item.get("twitterUrl")
                discord = item.get("discord") or item.get("discordUrl")

                end_date = item.get("endDate") or item.get("end_date")
                start_date = item.get("startDate") or item.get("start_date")

                desc_parts = []
                if item.get("description"):
                    desc_parts.append(item["description"][:300])
                if item.get("tasks"):
                    desc_parts.append(f"Tasks: {item['tasks']}")

                seen.add(name.lower())
                results.append({
                    "name": name,
                    "description": " | ".join(desc_parts)[:400],
                    "chain": chain,
                    "website": website,
                    "twitter": twitter,
                    "discord": discord,
                    "source": "cryptorank",
                    "token_symbol": item.get("tokenSymbol") or item.get("symbol"),
                    "status_raw": status,
                    "start_date": start_date,
                    "end_date": end_date,
                    # Include end_date so freshness filter in processor can use it
                    "listed_at": start_date,
                })

                if len(results) >= MAX_RESULTS:
                    break

    except Exception as e:
        logger.error("CryptoRank scrape error: %s", e)

    logger.info("CryptoRank: %d active airdrop campaigns found", len(results))
    return results
