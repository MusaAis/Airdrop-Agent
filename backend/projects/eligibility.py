import logging
from datetime import datetime, timezone
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models import (
    ProjectCriteria, Transaction, TaskConfig,
    TaskDailyProgress, Wallet, WalletBalance,
)

logger = logging.getLogger("airdrop.eligibility")


async def compute_eligibility(
    db: AsyncSession, project_id: int, wallet: Wallet
) -> Dict:
    criteria_result = await db.execute(
        select(ProjectCriteria).where(ProjectCriteria.project_id == project_id)
    )
    criteria = criteria_result.scalars().all()

    if not criteria:
        return {
            "project_id": project_id,
            "wallet": wallet.address,
            "progress_pct": 0,
            "met_count": 0,
            "total_criteria": 0,
            "criteria_detail": [],
            "stats": {},
        }

    # Fetch all confirmed txs for this wallet on this project
    task_ids_result = await db.execute(
        select(TaskConfig.id).where(TaskConfig.project_id == project_id)
    )
    task_ids = [r[0] for r in task_ids_result.all()]

    txs = []
    if task_ids:
        txs_result = await db.execute(
            select(Transaction).where(
                Transaction.wallet_id == wallet.id,
                Transaction.status == "confirmed",
                Transaction.task_config_id.in_(task_ids),
            )
        )
        txs = txs_result.scalars().all()

    tx_count = len(txs)
    unique_days = set()
    for tx in txs:
        if tx.confirmed_at:
            unique_days.add(tx.confirmed_at.date())

    # Get task types for interacted tasks
    interacted_task_configs = {}
    if task_ids:
        tc_result = await db.execute(
            select(TaskConfig).where(TaskConfig.id.in_(task_ids))
        )
        for tc in tc_result.scalars().all():
            interacted_task_configs[tc.id] = tc

    unique_task_types = set(
        interacted_task_configs[t.task_config_id].task_type
        for t in txs
        if t.task_config_id in interacted_task_configs
    )

    criteria_detail = []
    met_ids = []

    for c in criteria:
        detail = await _check_criterion(
            c, tx_count, unique_days, unique_task_types, txs, wallet, db
        )
        criteria_detail.append(detail)
        if detail["met"]:
            met_ids.append(c.id)

    progress_pct = (len(met_ids) / len(criteria)) * 100 if criteria else 0

    return {
        "project_id": project_id,
        "wallet": wallet.address,
        "progress_pct": round(progress_pct, 1),
        "met_count": len(met_ids),
        "total_criteria": len(criteria),
        "criteria_detail": criteria_detail,
        "stats": {
            "tx_count": tx_count,
            "active_days": len(unique_days),
            "unique_task_types": list(unique_task_types),
        },
    }


async def _check_criterion(
    c: ProjectCriteria,
    tx_count: int,
    unique_days: set,
    unique_task_types: set,
    txs: list,
    wallet: Wallet,
    db: AsyncSession,
) -> Dict:
    ctype = c.type
    threshold = c.threshold or 0
    current_value = 0
    met = False

    if ctype == "tx_count":
        current_value = tx_count
        met = tx_count >= threshold

    elif ctype == "volume":
        # Sum gas_cost_usd as a volume proxy until amount_usd per tx is tracked
        # A future improvement: store swap/bridge amount in USD in the Transaction model
        total_usd = sum(t.gas_cost_usd or 0 for t in txs)
        current_value = round(total_usd, 2)
        met = current_value >= threshold

    elif ctype == "time":
        current_value = len(unique_days)
        met = current_value >= threshold

    elif ctype == "governance":
        gov_count = sum(1 for t in txs if "vote" in str(unique_task_types) or "govern" in str(unique_task_types))
        current_value = gov_count
        met = gov_count >= threshold

    elif ctype == "token_hold":
        # Use cached wallet balances
        bal_result = await db.execute(
            select(WalletBalance).where(WalletBalance.wallet_id == wallet.id)
        )
        balances = bal_result.scalars().all()
        total_usd = sum(b.usd_value or 0 for b in balances)
        current_value = round(total_usd, 2)
        met = current_value >= threshold

    elif ctype == "social":
        # Social tasks cannot be verified on-chain
        # Mark uncertain criteria as not blocking
        current_value = 0
        met = c.uncertain  # uncertain social criteria don't block progress

    else:
        # Generic fallback: use tx_count
        current_value = tx_count
        met = tx_count >= threshold

    return {
        "criterion_id": c.id,
        "type": ctype,
        "description": c.description,
        "threshold": threshold,
        "unit": c.unit,
        "current_value": current_value,
        "met": met,
        "uncertain": c.uncertain,
        "source_quote": c.source_quote,
    }
