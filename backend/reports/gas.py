from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models import Transaction, Wallet, Chain

async def get_gas_usage_report(db: AsyncSession, chain_id: int = None):
    stmt = select(
        Wallet.address,
        Chain.name.label("chain"),
        func.sum(Transaction.gas_cost_usd).label("total_usd"),
        func.count(Transaction.id).label("tx_count")
    ).join(Chain, Transaction.chain_id == Chain.id)\
     .join(Wallet, Transaction.wallet_id == Wallet.id)\
     .where(Transaction.status == 'confirmed')

    if chain_id:
        stmt = stmt.where(Chain.id == chain_id)

    stmt = stmt.group_by(Wallet.address, Chain.name)
    result = await db.execute(stmt)
    return [{"wallet": r.address, "chain": r.chain, "total_gas_usd": round(r.total_usd or 0, 2), "tx_count": r.tx_count} for r in result.all()]
