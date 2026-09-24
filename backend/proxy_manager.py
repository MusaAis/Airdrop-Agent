import logging
from typing import Optional
from backend.models import Proxy
from backend.database import async_session
from sqlalchemy import select

logger = logging.getLogger("airdrop.proxy")

async def get_assigned_proxy(wallet_id: int) -> Optional[dict]:
    """Return proxy URL if assigned to wallet, else None."""
    async with async_session() as db:
        proxy = (await db.execute(
            select(Proxy).where(Proxy.wallet_id == wallet_id, Proxy.is_active == True)
        )).scalar_one_or_none()
        if proxy:
            return {"http": proxy.url, "https": proxy.url}
    return None

async def rotate_proxy(wallet_id: int) -> Optional[str]:
    """Rotate to next available proxy for wallet."""
    async with async_session() as db:
        current = (await db.execute(
            select(Proxy).where(Proxy.wallet_id == wallet_id)
        )).scalar_one_or_none()
        # Simple rotation: pick another active proxy
        all_proxies = (await db.execute(
            select(Proxy).where(Proxy.is_active == True)
        )).scalars().all()
        if len(all_proxies) > 1:
            for p in all_proxies:
                if p.id != current.id:
                    p.wallet_id = wallet_id
                    current.wallet_id = None
                    await db.commit()
                    return p.url
    return None
