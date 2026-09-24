"""
airdrops.io scraper — the most airdrop-specific source.

airdrops.io is server-side rendered HTML (unlike CryptoRank/RootData which
are React SPAs), so BeautifulSoup scraping actually works here.

We scrape /latest/ for new listings and also check the page structure
with fallback selectors since sites update their markup.

Guards:
  - No name → skip
  - Name too short (< 2 chars) → skip (navigation artifacts)
  - Description contains ended signals → skip
  - Hard cap MAX_RESULTS
"""

import httpx
import logging
from typing import List, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger("airdrop.discovery.airdrops_io")

URLS = [
    "https://airdrops.io/latest/",
    "https://airdrops.io/hot/",       # also check hot/trending
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RESULTS = 20

_ENDED_SIGNALS = {
    "ended", "finished", "completed", "airdrop over",
    "claim period ended", "snapshot taken", "tge done",
}


def _parse_page(html: str, source_url: str) -> List[Dict]:
    """Extract project cards from airdrops.io HTML."""
    soup = BeautifulSoup(html, "lxml")
    results = []
    seen: set = set()

    # airdrops.io uses <article> tags for each airdrop card
    # Fallback: look for divs with class containing "airdrop"
    cards = (
        soup.find_all("article")
        or soup.find_all("div", class_=lambda x: x and "airdrop" in " ".join(x).lower())
        or soup.find_all("div", class_=lambda x: x and "card" in " ".join(x).lower())
    )

    for card in cards:
        try:
            # Name: usually h2, h3, or the first strong/a inside the card
            name_el = (
                card.find("h2")
                or card.find("h3")
                or card.find("h1")
                or card.find("strong")
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 2:
                continue
            if name.lower() in seen:
                continue

            # Description: first <p> in the card
            desc_el = card.find("p")
            desc = desc_el.get_text(strip=True)[:400] if desc_el else ""

            # Skip if description signals it ended
            desc_lower = desc.lower()
            if any(sig in desc_lower for sig in _ENDED_SIGNALS):
                continue

            # Website link — prefer external links over internal nav
            links = card.find_all("a", href=True)
            website = None
            for link in links:
                href = link["href"]
                if href.startswith("http") and "airdrops.io" not in href:
                    website = href
                    break
            if not website:
                # Fall back to any link in the card
                link_el = card.find("a", href=True)
                website = link_el["href"] if link_el else None

            # Chain — some cards list the chain explicitly
            chain = "Unknown"
            chain_el = card.find(class_=lambda x: x and "chain" in " ".join(x or []).lower())
            if chain_el:
                chain = chain_el.get_text(strip=True) or "Unknown"

            seen.add(name.lower())
            results.append({
                "name": name,
                "description": desc,
                "chain": chain,
                "website": website,
                "source": "airdrops_io",
                "token_symbol": None,
                "source_url": source_url,
            })

            if len(results) >= MAX_RESULTS:
                break

        except Exception as e:
            logger.debug("airdrops.io card parse error: %s", e)
            continue

    return results


async def scrape() -> List[Dict]:
    all_results: List[Dict] = []
    seen_names: set = set()

    try:
        async with httpx.AsyncClient(
            timeout=30, headers=HEADERS, follow_redirects=True
        ) as client:
            for url in URLS:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning("airdrops.io %s returned HTTP %d", url, resp.status_code)
                        continue

                    page_results = _parse_page(resp.text, url)
                    for r in page_results:
                        if r["name"].lower() not in seen_names:
                            seen_names.add(r["name"].lower())
                            all_results.append(r)

                except Exception as e:
                    logger.warning("airdrops.io error fetching %s: %s", url, e)
                    continue

    except Exception as e:
        logger.error("airdrops.io scrape error: %s", e)

    logger.info("airdrops.io: %d projects found", len(all_results))
    return all_results
