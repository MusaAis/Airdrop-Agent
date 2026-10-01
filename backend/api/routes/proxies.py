import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.security.auth import verify_token
from backend.models import Proxy, Wallet
from backend.proxy_manager import client_proxy_kwargs, mask_proxy_url

router = APIRouter(prefix="/proxies", tags=["proxies"])

_SCHEMES = ("http", "https", "socks5", "socks5h")


class ProxyCreate(BaseModel):
    url: str
    type: str = "http"


class AssignRequest(BaseModel):
    wallet_id: Optional[int] = None   # null = unassign


class ActiveRequest(BaseModel):
    active: bool


def _out(p: Proxy) -> dict:
    return {
        "id": p.id, "url": mask_proxy_url(p.url), "type": p.type, "wallet_id": p.wallet_id,
        "is_active": p.is_active,
        "last_verified": p.last_verified.isoformat() if p.last_verified else None,
    }


@router.get("/")
async def list_proxies(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Proxy).order_by(Proxy.id))).scalars().all()
    return [_out(p) for p in rows]


@router.post("/")
async def add_proxy(data: ProxyCreate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    p = urlparse(data.url.strip())
    if p.scheme not in _SCHEMES or not p.hostname:
        raise HTTPException(400, f"URL must look like scheme://[user:pass@]host:port with scheme in {_SCHEMES}")
    proxy = Proxy(url=data.url.strip(), type=data.type.strip() or "http", is_active=True)
    db.add(proxy)
    await db.commit()
    await db.refresh(proxy)
    return _out(proxy)


@router.put("/{proxy_id}/assign")
async def assign_proxy(proxy_id: int, data: AssignRequest, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """One proxy per wallet, one wallet per proxy (sharing an IP across wallets is a Sybil signal)."""
    proxy = await db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(404, "Proxy not found")
    if data.wallet_id is None:
        proxy.wallet_id = None
    else:
        if not await db.get(Wallet, data.wallet_id):
            raise HTTPException(404, "Wallet not found")
        others = (await db.execute(
            select(Proxy).where(Proxy.wallet_id == data.wallet_id, Proxy.id != proxy_id)
        )).scalars().all()
        for o in others:
            o.wallet_id = None
        proxy.wallet_id = data.wallet_id
    await db.commit()
    return _out(proxy)


@router.put("/{proxy_id}/active")
async def set_active(proxy_id: int, data: ActiveRequest, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    proxy = await db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(404, "Proxy not found")
    proxy.is_active = data.active
    await db.commit()
    return _out(proxy)


@router.delete("/{proxy_id}")
async def delete_proxy(proxy_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    proxy = await db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(404, "Proxy not found")
    await db.delete(proxy)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/{proxy_id}/test")
async def test_proxy(proxy_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Fetch our public IP through the proxy. Records last_verified on success."""
    proxy = await db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(404, "Proxy not found")
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=12, **client_proxy_kwargs(proxy.url)) as client:
            r = await client.get("https://api.ipify.org?format=json")
            r.raise_for_status()
            ip = r.json().get("ip")
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    proxy.last_verified = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    return {"ok": True, "ip": ip, "latency_ms": int((time.monotonic() - start) * 1000)}
