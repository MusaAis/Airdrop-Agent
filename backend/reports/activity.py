from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.models import Transaction, Wallet, Chain, TaskConfig, Project
from datetime import datetime, timedelta, timezone

async def get_activity_log(db: AsyncSession, hours: int = 24, wallet_id: int = None):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(Transaction).where(Transaction.created_at >= since)
    if wallet_id:
        stmt = stmt.where(Transaction.wallet_id == wallet_id)
    stmt = stmt.order_by(desc(Transaction.created_at)).limit(500)
    txs = (await db.execute(stmt)).scalars().all()
    # Fetch related names
    result = []
    for tx in txs:
        wallet = await db.get(Wallet, tx.wallet_id) if tx.wallet_id else None
        chain = await db.get(Chain, tx.chain_id) if tx.chain_id else None
        task = await db.get(TaskConfig, tx.task_config_id) if tx.task_config_id else None
        proj = await db.get(Project, task.project_id) if task else None
        result.append({
            "id": tx.id,
            "wallet": wallet.address if wallet else "?",
            "chain": chain.name if chain else "?",
            "project": proj.name if proj else "?",
            "task_type": task.task_type if task else "?",
            "tx_hash": tx.tx_hash,
            "status": tx.status,
            "gas_cost_usd": tx.gas_cost_usd,
            "created_at": str(tx.created_at)
        })
    return result
