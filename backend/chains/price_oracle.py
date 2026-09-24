import httpx, logging, os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("airdrop.price_oracle")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_cache = {}

async def get_usd_price(symbol: str) -> Optional[float]:
    now = datetime.now(timezone.utc)
    if symbol in _cache:
        price, ts = _cache[symbol]
        if (now - ts) < timedelta(minutes=5):
            return price
    try:
        url = f"{COINGECKO_BASE}/simple/price?ids={symbol.lower()}&vs_currencies=usd"
        headers = {"User-Agent": "AirdropAgent/1.0"}
        if COINGECKO_API_KEY:
            headers["x-cg-pro-api-key"] = COINGECKO_API_KEY
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if symbol.lower() in data and "usd" in data[symbol.lower()]:
                    price = data[symbol.lower()]["usd"]
                    _cache[symbol] = (price, now)
                    return price
            elif resp.status_code == 429:
                logger.warning("CoinGecko rate limited")
    except Exception as e:
        logger.error(f"Price fetch error: {e}")
    return None
