from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from backend.models import Wallet

async def mark_wallet_selected(db: AsyncSession, wallet: Wallet):
    wallet.last_selected_at = datetime.now(timezone.utc)
    await db.commit()

async def get_least_recently_used_wallet(db: AsyncSession, eligible_wallets: list) -> Wallet:
    """Return wallet with oldest last_selected_at (or None) from list."""
    candidates = [w for w in eligible_wallets if w.status == "active"]
    if not candidates:
        return None
    # Sort by last_selected_at ascending (None first)
    candidates.sort(key=lambda w: (w.last_selected_at is None, w.last_selected_at))
    return candidates[0]
