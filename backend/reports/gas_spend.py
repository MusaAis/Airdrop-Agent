from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models import Transaction, Wallet, Project, TaskConfig

async def get_gas_spend_report(db: AsyncSession, project_id: int = None):
    """
    Factual gas spend per wallet per project — confirmed transactions only.
    This replaces the old ROI report, which paired real gas cost against an
    AI-guessed "estimated_token_value_usd" that was always hardcoded to 0
    (see PLAN.md §3 — the ROI estimator was removed). This keeps only the
    factual half: what was actually spent, with no guessed value attached.
    """
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

    return [
        {
            "wallet": row.address,
            "project": row.name,
            "gas_spent_usd": round(row.total_gas or 0, 2),
            "transactions": row.tx_count,
        }
        for row in rows
    ]
