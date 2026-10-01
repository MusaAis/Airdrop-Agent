import logging
import random
from typing import Optional
from urllib.parse import urlparse

from backend.models import Proxy
from backend.database import async_session
from sqlalchemy import select

logger = logging.getLogger("airdrop.proxy")


def client_proxy_kwargs(proxy_url: Optional[str]) -> dict:
    """httpx renamed AsyncClient(proxies=...) to proxy=... (0.26) and removed the
    old name (0.28). Pick whichever this install supports."""
    if not proxy_url:
        return {}
    import inspect
    import httpx
    params = inspect.signature(httpx.AsyncClient.__init__).parameters
    return {"proxy": proxy_url} if "proxy" in params else {"proxies": proxy_url}


def mask_proxy_url(url: str) -> str:
    """Never show proxy passwords in the UI or API responses."""
    try:
        p = urlparse(url)
        if p.password:
            host = p.hostname or ""
            port = f":{p.port}" if p.port else ""
            return f"{p.scheme}://{p.username}:***@{host}{port}"
    except Exception:
        pass
    return url


async def get_assigned_proxy(wallet_id: int) -> Optional[dict]:
    """Return proxy URL if assigned to wallet, else None."""
    async with async_session() as db:
        proxy = (await db.execute(
            select(Proxy).where(Proxy.wallet_id == wallet_id, Proxy.is_active == True)
        )).scalars().first()
        if proxy:
            return {"http": proxy.url, "https": proxy.url}
    return None


async def rotate_proxy(wallet_id: int) -> Optional[str]:
    """Move a wallet to a different ACTIVE proxy that is not assigned to anyone.
    (The old version took another wallet's proxy and crashed when the wallet had
    no proxy yet.) Returns the new proxy URL, or None if none is free."""
    async with async_session() as db:
        current = (await db.execute(
            select(Proxy).where(Proxy.wallet_id == wallet_id)
        )).scalars().all()
        free = (await db.execute(
            select(Proxy).where(Proxy.is_active == True, Proxy.wallet_id == None)
        )).scalars().all()
        if not free:
            return None
        new = random.choice(free)
        for p in current:
            p.wallet_id = None
        new.wallet_id = wallet_id
        await db.commit()
        return new.url
