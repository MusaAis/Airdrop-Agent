from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Wallet
from backend.wallet.sybil_detector import compute_wallet_correlations


async def get_sybil_report(db: AsyncSession) -> dict:
    """Full Sybil risk report: per-wallet scores + suspicious pairs."""
    # Run correlation analysis and update wallet scores
    pairs = await compute_wallet_correlations(db)

    # Fetch all wallets with non-zero sybil scores
    result = await db.execute(
        select(Wallet).where(Wallet.sybil_risk_score > 0).order_by(Wallet.sybil_risk_score.desc())
    )
    risky_wallets = result.scalars().all()

    return {
        "high_risk_wallets": [
            {
                "wallet_id": w.id,
                "address": w.address,
                "risk_score": w.sybil_risk_score,
                "health_score": w.health_score,
                "status": w.status,
            }
            for w in risky_wallets
        ],
        "suspicious_pairs": pairs,
        "total_wallets_flagged": len(risky_wallets),
        "total_suspicious_pairs": len(pairs),
    }

