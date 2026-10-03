from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models import Transaction, Wallet, Project, TaskConfig

async def get_gas_spend_report(db: AsyncSession, project_id: int = None):
    """
    Factual gas spend per wallet per project. `gas_spent_native` is the fee paid per gas token
    (includes reverted transactions, which still burn gas); `gas_spent_usd` is a price estimate
    for confirmed transactions only and is meaningless on testnets.
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

    nstmt = select(
        Wallet.address, Project.name, Transaction.gas_token, func.sum(Transaction.gas_cost_native)
    ).join(TaskConfig, Transaction.task_config_id == TaskConfig.id)\
     .join(Project, TaskConfig.project_id == Project.id)\
     .join(Wallet, Transaction.wallet_id == Wallet.id)\
     .where(Transaction.gas_cost_native.is_not(None))
    if project_id:
        nstmt = nstmt.where(Project.id == project_id)
    native: dict = {}
    for addr, pname, sym, total in (await db.execute(nstmt.group_by(Wallet.address, Project.name, Transaction.gas_token))).all():
        if total:
            native.setdefault((addr, pname), {})[sym or "?"] = round(float(total), 8)

    return [
        {
            "wallet": row.address,
            "project": row.name,
            "gas_spent_usd": round(row.total_gas or 0, 2),
            "gas_spent_native": native.get((row.address, row.name), {}),
            "transactions": row.tx_count,
        }
        for row in rows
    ]
