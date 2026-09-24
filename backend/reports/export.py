from sqlalchemy import select
import csv
import io
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Transaction, Wallet, Chain, Project, TaskConfig

async def export_csv(db: AsyncSession, table: str) -> str:
    """Export specified table as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    if table == "transactions":
        writer.writerow(["id", "wallet", "chain", "project", "task_type", "tx_hash", "status", "gas_cost_usd", "created_at"])
        txs = (await db.execute(select(Transaction).limit(10000))).scalars().all()
        for tx in txs:
            wallet = await db.get(Wallet, tx.wallet_id) if tx.wallet_id else None
            chain = await db.get(Chain, tx.chain_id) if tx.chain_id else None
            task = await db.get(TaskConfig, tx.task_config_id) if tx.task_config_id else None
            proj = await db.get(Project, task.project_id) if task else None
            writer.writerow([
                tx.id,
                wallet.address if wallet else "",
                chain.name if chain else "",
                proj.name if proj else "",
                task.task_type if task else "",
                tx.tx_hash,
                tx.status,
                tx.gas_cost_usd or "",
                str(tx.created_at)
            ])
    elif table == "wallets":
        writer.writerow(["id", "address", "status", "health_score", "gas_wallet", "created_at"])
        wallets = (await db.execute(select(Wallet))).scalars().all()
        for w in wallets:
            writer.writerow([w.id, w.address, w.status, w.health_score, w.is_gas_wallet, str(w.created_at)])
    # Add other tables as needed
    return output.getvalue()
