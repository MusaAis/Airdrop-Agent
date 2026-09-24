"""
Cooldown tracker for faucet requests.
Checks DB to ensure we don't re-request before the faucet's cooldown period.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import FaucetRequest, Faucet


async def is_on_cooldown(
    db: AsyncSession,
    wallet_id: int,
    faucet_id: int,
    cooldown_hours: int,
) -> bool:
    """
    Returns True if the wallet made a successful faucet request
    within the last cooldown_hours for this faucet.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
    result = await db.execute(
        select(FaucetRequest).where(
            FaucetRequest.wallet_id == wallet_id,
            FaucetRequest.faucet_id == faucet_id,
            FaucetRequest.status == "success",
            FaucetRequest.requested_at >= cutoff,
        ).order_by(FaucetRequest.requested_at.desc()).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def time_until_cooldown_expires(
    db: AsyncSession,
    wallet_id: int,
    faucet_id: int,
    cooldown_hours: int,
) -> Optional[timedelta]:
    """
    Returns how much time remains on the cooldown, or None if not on cooldown.
    """
    result = await db.execute(
        select(FaucetRequest).where(
            FaucetRequest.wallet_id == wallet_id,
            FaucetRequest.faucet_id == faucet_id,
            FaucetRequest.status == "success",
        ).order_by(FaucetRequest.requested_at.desc()).limit(1)
    )
    last = result.scalar_one_or_none()
    if not last:
        return None

    expires_at = last.requested_at + timedelta(hours=cooldown_hours)
    now = datetime.now(timezone.utc)
    if expires_at > now:
        return expires_at - now
    return None


async def get_cooldown_status_for_wallet(
    db: AsyncSession, wallet_id: int
) -> list:
    """
    Returns cooldown status for all faucets for a given wallet.
    Used by the Telegram `faucet.status` command.
    """
    result = await db.execute(select(Faucet).where(Faucet.enabled == True))
    faucets = result.scalars().all()

    statuses = []
    for faucet in faucets:
        remaining = await time_until_cooldown_expires(
            db, wallet_id, faucet.id, faucet.cooldown_hours
        )
        statuses.append({
            "faucet_id": faucet.id,
            "faucet_name": faucet.name,
            "chain_id": faucet.chain_id,
            "cooldown_hours": faucet.cooldown_hours,
            "on_cooldown": remaining is not None,
            "remaining_minutes": int(remaining.total_seconds() / 60) if remaining else 0,
        })
    return statuses
