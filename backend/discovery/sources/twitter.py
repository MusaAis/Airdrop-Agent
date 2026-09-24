"""
Twitter/X airdrop discovery — via curated crypto account RSS feeds.

The old version searched Nitter instances for generic keywords like "airdrop"
and tried to extract project names by taking "the first capitalized word near
airdrop". This returned garbage: words like "Join", "The", "This", "Get",
"Testnet", etc. Not project names.

Problems with the old approach:
  1. Nitter public instances are unreliable (constantly going down)
  2. Generic keyword search returns thousands of spam tweets
  3. Extracting project names from tweet text via capitalization is noise
  4. A random tweet saying "airdrop" has zero signal value

This version:
  1. Monitors CURATED accounts that reliably post airdrop opportunities
     (airdrop aggregators, crypto researchers, protocol accounts)
  2. Uses Nitter's RSS feed per account — much more reliable than search
  3. Parses the RSS XML properly
  4. Falls back gracefully if all Nitter instances are down
  5. Limits to recent posts only (last 48 hours)

The extracted data is intentionally thin — chain/website will be Unknown/null
because tweet text rarely has them. The AI pre-screen will handle evaluation.
The key signal from Twitter is the PROJECT NAME from the post title/text.
"""

import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from email.utils import parsedate_to_datetime

logger = logging.getLogger("airdrop.discovery.twitter")

# Nitter instances to try (in order)
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.net",
    "https://nitter.1d4.us",
    "https://nitter.poast.org",
]

# Curated accounts that post reliable airdrop/testnet opportunities
# These are aggregator accounts, researchers, and protocol trackers
# NOT generic crypto influencers
CURATED_ACCOUNTS = [
    "airdropbob",
    "AirdropAlert",
    "earni_fi",
    "defi_airdrops",
    "CryptoRank_io",
    "lootingdefi",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, text/xml, application/xml",
}

# Only include tweets from the last 48 hours
MAX_AGE_HOURS = 48
MAX_RESULTS = 15

# Keywords that must appear for a tweet to be considered airdrop-relevant
RELEVANCE_KEYWORDS = {
    "airdrop", "testnet", "farming", "eligibility", "campaign",
    "task", "points", "incentive", "retroactive",
}

# Noise words that should NOT be mistaken for project names
# (capitalized words that appear near "airdrop" but aren't projects)
_NOISE_WORDS = {
    "The", "This", "Join", "Get", "Claim", "Check", "How", "New",
    "Free", "Don", "Follow", "Now", "Earn", "Use", "Read", "Watch",
    "Learn", "All", "Are", "Can", "Just", "Here", "See", "Top",
    "Best", "You", "Your", "Our", "One", "Two", "For", "With",
    "From", "About", "More", "Also", "And", "But", "Not", "Has",
    "Have", "Will", "Was", "Its", "They", "Their", "Into", "Over",
}


def _is_recent(date_str: str) -> bool:
    """Check if RSS item pubDate is within MAX_AGE_HOURS."""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
        return dt > cutoff
    except Exception:
        return True  # Can't parse date — include it


def _extract_project_name(title: str, content: str) -> Optional[str]:
    """
    Extract a likely project name from tweet title/content.
    Looks for capitalized words 2–20 chars long that aren't noise words.
    Returns the first good candidate or None.
    """
    text = f"{title} {content}"
    words = text.split()
    for word in words:
        # Clean punctuation
        clean = word.strip(".,!?:;()[]@#$%&*\"'")
        if (
            len(clean) >= 3
            and len(clean) <= 20
            and clean[0].isupper()
            and clean not in _NOISE_WORDS
            and not clean.startswith("http")
            and not clean.startswith("@")
            and not clean.startswith("#")
            and not clean.isupper()  # skip ALL_CAPS (usually tickers, not names)
        ):
            return clean
    return None


def _is_relevant(text: str) -> bool:
    """Check if tweet text contains at least one airdrop-relevance keyword."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in RELEVANCE_KEYWORDS)


async def _fetch_rss(
    client: httpx.AsyncClient,
    instance: str,
    account: str,
) -> List[Dict]:
    """Fetch and parse Nitter RSS feed for one account."""
    results = []
    try:
        url = f"{instance}/{account}/rss"
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200:
            return []

        # Parse RSS XML
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            logger.debug("RSS XML parse error for %s/%s: %s", instance, account, e)
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        channel = root.find("channel")
        if channel is None:
            return []

        items = channel.findall("item")
        for item in items[:20]:  # check up to 20 most recent tweets per account
            try:
                title = (item.findtext("title") or "").strip()
                content = (item.findtext("description") or "").strip()
                pub_date = item.findtext("pubDate") or ""
                link = item.findtext("link") or ""

                # Only recent tweets
                if pub_date and not _is_recent(pub_date):
                    continue

                full_text = f"{title} {content}"

                # Must be airdrop-relevant
                if not _is_relevant(full_text):
                    continue

                # Try to extract project name
                project_name = _extract_project_name(title, content)
                if not project_name:
                    # Use the account name + title as fallback identifier
                    project_name = f"{account}: {title[:40]}"

                results.append({
                    "name": project_name,
                    "description": f"[via @{account}] {content[:300]}",
                    "chain": "Unknown",
                    "website": None,
                    "source": "twitter_nitter",
                    "token_symbol": None,
                    "source_account": account,
                    "tweet_url": link,
                    "raw_text": full_text[:300],
                })

            except Exception as e:
                logger.debug("RSS item parse error: %s", e)
                continue

    except Exception as e:
        logger.debug("Nitter RSS fetch error (%s/%s): %s", instance, account, e)

    return results


async def scrape() -> List[Dict]:
    all_results: List[Dict] = []
    seen_names: set = set()

    try:
        async with httpx.AsyncClient(
            headers=HEADERS, follow_redirects=True
        ) as client:
            # Try each Nitter instance until one works
            working_instance: Optional[str] = None
            for instance in NITTER_INSTANCES:
                try:
                    # Quick connectivity check
                    test = await client.get(f"{instance}/robots.txt", timeout=8)
                    if test.status_code < 500:
                        working_instance = instance
                        break
                except Exception:
                    continue

            if not working_instance:
                logger.warning(
                    "Twitter/Nitter: no working instance found from %d tried. "
                    "Returning empty results.",
                    len(NITTER_INSTANCES),
                )
                return []

            logger.info("Twitter/Nitter: using instance %s", working_instance)

            for account in CURATED_ACCOUNTS:
                try:
                    items = await _fetch_rss(client, working_instance, account)
                    for item in items:
                        name_lower = item["name"].lower()
                        if name_lower not in seen_names:
                            seen_names.add(name_lower)
                            all_results.append(item)
                            if len(all_results) >= MAX_RESULTS:
                                break
                except Exception as e:
                    logger.debug("Error processing account @%s: %s", account, e)
                    continue

                if len(all_results) >= MAX_RESULTS:
                    break

    except Exception as e:
        logger.error("Twitter scrape error: %s", e)

    logger.info(
        "Twitter/Nitter: %d relevant posts from %d curated accounts",
        len(all_results), len(CURATED_ACCOUNTS),
    )
    return all_results
