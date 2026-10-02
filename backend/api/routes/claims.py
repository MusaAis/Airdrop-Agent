"""
Read-only claim scanner for the website (Phase 9).

The Claims page used to call /claims/eligible, /claims/pending, /claims/trigger and
/claims/threshold, none of which existed. This replaces them with one honest endpoint:

    GET /claims/scan[?refresh=true]

It wraps claims.manager.scan_claimable_airdrops (on-chain view calls against each
project's "claim" contracts) and caches the result, because a scan makes one RPC call
per wallet per contract and can take a while.

Deliberately NOT here: any endpoint that sends a claim transaction. Claiming spends
real gas and is irreversible, and auto-claim was removed on purpose (PLAN.md §3).
A manual claim with a confirm step + dry-run is tracked in PLAN.md "Known, not built".
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.security.auth import verify_token
from backend.claims.manager import scan_claimable_airdrops

logger = logging.getLogger("airdrop.claims.api")
router = APIRouter(prefix="/claims", tags=["claims"])

CACHE_TTL_SECONDS = 10 * 60

_cache: dict = {"items": None, "scanned_at": None, "ts": 0.0, "error": None}
_lock = asyncio.Lock()


def _snapshot(cached: bool) -> dict:
    items = _cache["items"] or []
    return {
        "scanned_at": _cache["scanned_at"],
        "cached": cached,
        "error": _cache["error"],
        "count": len(items),
        "total_usd_estimate": round(sum(i.get("usd_estimate") or 0 for i in items), 2),
        "items": items,
    }


@router.get("/scan")
async def scan_claims(
    refresh: bool = False,
    _user: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    fresh_enough = _cache["items"] is not None and (time.time() - _cache["ts"]) < CACHE_TTL_SECONDS
    if fresh_enough and not refresh:
        return _snapshot(cached=True)

    # one scan at a time; a second caller waits and then reuses the result
    async with _lock:
        if _cache["items"] is not None and (time.time() - _cache["ts"]) < 15 and not _cache["error"]:
            return _snapshot(cached=True)
        try:
            items = await scan_claimable_airdrops(db)
            _cache.update(
                items=items, error=None, ts=time.time(),
                scanned_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:  # keep the last good result visible if a rescan fails
            logger.exception("claim scan failed")
            _cache["error"] = f"Scan failed: {e}"
            if _cache["items"] is None:
                _cache["items"] = []
        return _snapshot(cached=False)
