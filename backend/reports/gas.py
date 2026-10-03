from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models import Transaction, Wallet, Chain


async def get_gas_usage_report(db: AsyncSession, chain_id: int = None):
    """Gas per wallet per chain. `total_gas_native` / `gas_token` are factual (fee paid, in the
    chain's gas token, including reverted transactions); `total_gas_usd` is a price estimate
    that is meaningless on testnets (confirmed transactions only, as before)."""
    stmt = select(
        Wallet.address,
        Chain.name.label("chain"),
        Chain.gas_token_symbol.label("gas_token"),
        func.sum(Transaction.gas_cost_usd).label("total_usd"),
        func.sum(Transaction.gas_cost_native).label("total_native"),
        func.count(Transaction.id).label("tx_count"),
    ).join(Chain, Transaction.chain_id == Chain.id)\
     .join(Wallet, Transaction.wallet_id == Wallet.id)\
     .where(Transaction.status.in_(["confirmed", "failed"]), Transaction.gas_cost_native.is_not(None))

    if chain_id:
        stmt = stmt.where(Chain.id == chain_id)

    stmt = stmt.group_by(Wallet.address, Chain.name, Chain.gas_token_symbol)
    result = await db.execute(stmt)
    return [{
        "wallet": r.address, "chain": r.chain, "gas_token": r.gas_token,
        "total_gas_native": round(r.total_native or 0.0, 8),
        "total_gas_usd": round(r.total_usd or 0, 2),
        "tx_count": r.tx_count,
    } for r in result.all()]
