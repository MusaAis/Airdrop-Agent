"""
L2Beat scraper — discovers L2/L3 projects without a live token.

L2Beat publishes a public API at https://l2beat.com/api/scaling/summary
which returns structured JSON — far more reliable than HTML scraping.

L2Beat tracks rollup and validium projects. Many are live on mainnet with
real TVL but haven't launched a token yet. These are prime farming targets
(think: pre-airdrop zkSync era, pre-token StarkNet, etc.)

The old scraper used HTML table scraping on the React-rendered page — which
returns an empty table because the data is loaded client-side via JS.
This version uses the JSON API endpoint.

Guards:
  - Has a live token already → skip (no airdrop coming)
  - Stage == "Production" AND TVL > $2B → established, skip (likely already airdropped)
  - Stage == "UnderReview" → very new, might be interesting — keep
  - Hard cap MAX_RESULTS
"""

import httpx
import logging
from typing import List, Dict

logger = logging.getLogger("airdrop.discovery.l2beat")

# L2Beat public API — returns JSON without auth
API_URL = "https://l2beat.com/api/scaling/summary"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
}

MAX_RESULTS = 20

# TVL above this on an L2 that has NO token = very surprising.
# Usually means they already distributed (like Optimism, Arbitrum).
# We keep this low to catch mid-size projects that haven't launched yet.
SKIP_IF_TVL_ABOVE = 2_000_000_000  # $2B


async def scrape() -> List[Dict]:
    results = []
    try:
        async with httpx.AsyncClient(
            timeout=30, headers=HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(API_URL)

            if resp.status_code == 404:
                logger.warning(
                    "L2Beat API returned 404 — endpoint may have changed. "
                    "Check https://l2beat.com/api/ for current endpoints."
                )
                return []
            if resp.status_code != 200:
                logger.warning("L2Beat API returned HTTP %d", resp.status_code)
                return []

            data = resp.json()
            # API response shape: {"data": {"projects": [...]}} or {"projects": [...]}
            projects = (
                data.get("data", {}).get("projects")
                or data.get("projects")
                or []
            )

            seen: set = set()
            for p in projects:
                name = (p.get("name") or "").strip()
                if not name or name.lower() in seen:
                    continue

                # Skip if already has a live token
                token = p.get("tokenSymbol") or p.get("nativeToken") or p.get("token")
                if token and token not in ("-", "N/A", ""):
                    continue

                # Get TVL
                tvl_raw = p.get("tvl") or p.get("totalValueLocked") or {}
                if isinstance(tvl_raw, dict):
                    tvl = tvl_raw.get("value") or tvl_raw.get("usd") or 0
                else:
                    tvl = float(tvl_raw) if tvl_raw else 0

                # Skip mega-established projects (they already airdropped)
                if tvl > SKIP_IF_TVL_ABOVE:
                    continue

                stage = p.get("stage") or p.get("stageConfig", {}).get("stage") or "Unknown"
                category = p.get("category") or p.get("type") or "L2"
                website = p.get("website") or p.get("url") or f"https://l2beat.com/scaling/projects/{p.get('slug', '')}"

                seen.add(name.lower())
                results.append({
                    "name": name,
                    "description": (
                        f"L2/L3 scaling project on L2Beat. "
                        f"Category: {category}. Stage: {stage}. "
                        f"TVL: ${tvl:,.0f}. No token launched yet."
                    ),
                    "chain": "Ethereum L2",
                    "website": website,
                    "source": "l2beat",
                    "token_symbol": None,
                    "tvl_usd": tvl,
                    "stage": stage,
                    "category": category,
                })

                if len(results) >= MAX_RESULTS:
                    break

    except Exception as e:
        logger.error("L2Beat scrape error: %s", e)

    logger.info("L2Beat: %d token-less L2 projects found", len(results))
    return results
