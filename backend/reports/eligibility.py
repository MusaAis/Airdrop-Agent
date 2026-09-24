from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Project, Wallet, ProjectCriteria, Transaction, TaskConfig, TaskDailyProgress

async def get_eligibility_report(db: AsyncSession, project_id: int = None):
    """Return per-wallet eligibility % for each project."""
    projects_q = select(Project)
    if project_id:
        projects_q = projects_q.where(Project.id == project_id)
    projects = (await db.execute(projects_q)).scalars().all()

    wallets = (await db.execute(select(Wallet).where(Wallet.status == 'active'))).scalars().all()

    report = []
    for proj in projects:
        criteria = (await db.execute(select(ProjectCriteria).where(ProjectCriteria.project_id == proj.id))).scalars().all()
        if not criteria:
            continue
        for wallet in wallets:
            # Count met criteria: for each criterion, check if wallet has done a related task (simplified)
            met = 0
            for c in criteria:
                # In real implementation, you'd match criteria type with actual on-chain data.
                # Here we check if any transaction exists for this project and wallet.
                tx_count = (await db.execute(
                    select(Transaction).where(
                        Transaction.wallet_id == wallet.id,
                        Transaction.task_config_id.in_(
                            select(TaskConfig.id).where(TaskConfig.project_id == proj.id)
                        )
                    )
                )).scalars().all()
                if len(tx_count) > 0:
                    met += 1
            pct = (met / len(criteria)) * 100 if criteria else 0
            report.append({
                "project": proj.name,
                "wallet": wallet.address,
                "eligibility_pct": round(pct, 1),
                "met_criteria": met,
                "total_criteria": len(criteria)
            })
    return report
