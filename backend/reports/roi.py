from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models import Transaction, Wallet, Project, TaskConfig

async def get_roi_report(db: AsyncSession, project_id: int = None):
    """Gas spent vs estimated token value per wallet per project."""
    # Aggregate gas costs per wallet per project
    stmt = select(
        Wallet.address,
        Project.name,
        func.sum(Transaction.gas_cost_usd).label("total_gas"),
        func.count(Transaction.id).label("tx_count")
    ).join(TaskConfig, Transaction.task_config_id == TaskConfig.id)\
     .join(Project, TaskConfig.project_id == Project.id)\
     .join(Wallet, Transaction.wallet_id == Wallet.id)\
     .where(Transaction.status == 'confirmed')

    if project_id:
        stmt = stmt.where(Project.id == project_id)

    stmt = stmt.group_by(Wallet.address, Project.name)
    result = await db.execute(stmt)
    rows = result.all()

    report = []
    for row in rows:
        # For ROI, we'd need estimated airdrop value. This is a placeholder.
        estimated_value = 0  # would come from AI estimation
        report.append({
            "wallet": row.address,
            "project": row.name,
            "gas_spent_usd": round(row.total_gas or 0, 2),
            "transactions": row.tx_count,
            "estimated_token_value_usd": estimated_value,
            "net_roi": round(estimated_value - (row.total_gas or 0), 2)
        })
    return report
