"""
DeFiLlama scraper — finds mainnet protocols WITHOUT a live token yet.

These are legitimate airdrop candidates: protocols with real on-chain activity,
real TVL, but no token launched yet. The token-less filter is the key signal.

Correct use of TVL here:
  - TVL is a signal that the MAINNET protocol is real and active
  - We want NO token symbol (token_symbol null = potential future airdrop)
  - We filter TVL range to exclude dust projects and mega-established ones
  - This is NOT for testnet discovery — that comes from airdrops.io / cryptorank

Guards (cheapest first, before any AI call):
  1. Has token symbol → skip (already launched, no future airdrop)
  2. TVL < MIN_TVL → skip (too small / inactive / likely dead)
  3. TVL > MAX_TVL → skip (Uniswap-tier — they already did their airdrop years ago)
  4. Category in SKIP_CATEGORIES → skip (no farming value)
  5. TVL dropped >80% in 24h → skip (rug signal)
  6. Hard cap MAX_RESULTS — sorted by TVL, take top N only
"""

import httpx
import logging
from typing import List, Dict

logger = logging.getLogger("airdrop.discovery.defillama")

PROTOCOLS_URL = "https://api.llama.fi/protocols"

# TVL range: $100k minimum (has real users), $5B maximum (too established)
# Rationale: protocols that already did airdrops (Uniswap, Aave, etc.) have TVL
# in the tens of billions. Mid-range is where new potential airdrops live.
MIN_TVL = 100_000       # $100k — has real activity
MAX_TVL = 5_000_000_000  # $5B — above this they almost certainly already launched a token

# Categories where airdrop farming produces no value
SKIP_CATEGORIES = {
    "CEX",               # centralised exchanges — no on-chain farming
    "RWA",               # real world assets — KYC required, not farmable
    "Indexes",           # index funds — passive, no interaction farming
    "Yield Aggregator",  # these auto-compound, no manual farming needed
    "Chain",             # L1 chains themselves — not protocols
}

# Hard cap: protects AI quota. Top N by TVL only.
MAX_RESULTS = 25


async def scrape() -> List[Dict]:
    results = []
    total_checked = 0
    try:
        async with httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": "AirdropAgent/1.0"},
        ) as client:
            resp = await client.get(PROTOCOLS_URL)
            if resp.status_code != 200:
                logger.warning("DeFiLlama returned HTTP %d", resp.status_code)
                return []

            protocols = resp.json()
            candidates = []
            total_checked = len(protocols)

            for p in protocols:
                # Guard 1: already has a token — not a future airdrop candidate
                symbol = (p.get("symbol") or "").strip()
                if symbol and symbol not in ("-", "N/A", ""):
                    continue

                # Guard 2 & 3: TVL range
                tvl = p.get("tvl") or 0
                if not (MIN_TVL <= tvl <= MAX_TVL):
                    continue

                # Guard 4: useless categories
                category = (p.get("category") or "").strip()
                if category in SKIP_CATEGORIES:
                    continue

                # Guard 5: TVL rug signal (crashed >80% in 24h)
                change_1d = p.get("change_1d") or 0
                if change_1d < -80:
                    logger.debug(
                        "DeFiLlama: skipping %s — TVL dropped %.0f%% in 24h",
                        p.get("name"), abs(change_1d),
                    )
                    continue

                chains = p.get("chains") or []
                primary_chain = chains[0] if chains else (p.get("chain") or "Unknown")

                candidates.append({
                    "name": p.get("name"),
                    "description": (p.get("description") or "")[:400],
                    "chain": primary_chain,
                    "all_chains": chains[:5],         # top 5 chains this protocol runs on
                    "tvl_usd": tvl,
                    "tvl_change_24h_pct": change_1d,
                    "website": p.get("url"),
                    "category": category,
                    "source": "defillama",
                    "token_symbol": None,              # confirmed: no token yet
                    # Note: DeFiLlama protocol list has no date field.
                    # Freshness filter in processor gives benefit-of-the-doubt
                    # when no date is present — AI pre-screen catches stale ones.
                })

            # Sort by TVL descending: most active real protocols first
            candidates.sort(key=lambda x: x["tvl_usd"], reverse=True)

            # Dedup by lowercase name within this batch
            seen: set = set()
            for c in candidates:
                n = (c["name"] or "").lower().strip()
                if n and n not in seen:
                    seen.add(n)
                    results.append(c)
                    if len(results) >= MAX_RESULTS:
                        break

    except Exception as e:
        logger.error("DeFiLlama scrape error: %s", e)

    logger.info(
        "DeFiLlama: %d candidates (from %d protocols, capped at %d)",
        len(results), total_checked, MAX_RESULTS,
    )
    return results
