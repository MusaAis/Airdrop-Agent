"""
Metric-driven tasks: track progress toward targets like total volume,
tx count, active days, unique contracts. These don't send a single
transaction — they evaluate current DB state and trigger the appropriate
underlying task until the metric target is reached.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct
from backend.models import Transaction, TaskConfig, Log, WalletBalance, ChainToken

logger = logging.getLogger("airdrop.metric_tasks")


async def evaluate_metric(
    db: AsyncSession,
    wallet_id: int,
    task_config: TaskConfig,
    project_id: int,
) -> Dict:
    """
    Evaluate a metric task and return current progress.
    Returns: {metric, current_value, target, completed, pct}
    """
    params = task_config.parameters or {}
    metric_type = task_config.task_type

    if metric_type == "achieve_tx_count":
        return await _check_tx_count(db, wallet_id, task_config, params)

    elif metric_type == "achieve_volume":
        return await _check_volume(db, wallet_id, task_config, params)

    elif metric_type == "achieve_active_days":
        return await _check_active_days(db, wallet_id, task_config, params)

    elif metric_type == "achieve_unique_contracts":
        return await _check_unique_contracts(db, wallet_id, task_config, params)

    elif metric_type == "achieve_unique_chains":
        return await _check_unique_chains(db, wallet_id, task_config, params)

    elif metric_type == "maintain_balance":
        return await _check_balance(db, wallet_id, task_config, params)

    return {"metric": metric_type, "current_value": 0, "target": 0, "completed": False, "pct": 0}


async def _check_tx_count(db, wallet_id, task_config, params) -> Dict:
    target = int(params.get("target_count", task_config.daily_tx_max or 10))
    result = await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.wallet_id == wallet_id,
            Transaction.task_config_id == task_config.id,
            Transaction.status == "confirmed",
        )
    )
    current = result.scalar() or 0
    return {
        "metric": "achieve_tx_count",
        "current_value": current,
        "target": target,
        "completed": current >= target,
        "pct": min(100, round(current / target * 100, 1)) if target else 0,
    }


async def _check_volume(db, wallet_id, task_config, params) -> Dict:
    """Track total USD volume of confirmed transactions."""
    target_usd = float(params.get("target_usd", 100.0))
    result = await db.execute(
        select(func.sum(Transaction.gas_cost_usd)).where(
            Transaction.wallet_id == wallet_id,
            Transaction.task_config_id == task_config.id,
            Transaction.status == "confirmed",
        )
    )
    # gas_cost_usd is a proxy for volume tracking; in production this would
    # use actual swap amounts stored in a separate table
    current_usd = float(result.scalar() or 0.0)
    return {
        "metric": "achieve_volume",
        "current_value": current_usd,
        "target": target_usd,
        "completed": current_usd >= target_usd,
        "pct": min(100, round(current_usd / target_usd * 100, 1)) if target_usd else 0,
        "unit": "USD",
    }


async def _check_active_days(db, wallet_id, task_config, params) -> Dict:
    """Count unique calendar days wallet had at least one confirmed tx."""
    target_days = int(params.get("target_days", 7))
    result = await db.execute(
        select(func.count(distinct(func.date(Transaction.confirmed_at)))).where(
            Transaction.wallet_id == wallet_id,
            Transaction.status == "confirmed",
        )
    )
    current_days = result.scalar() or 0
    return {
        "metric": "achieve_active_days",
        "current_value": current_days,
        "target": target_days,
        "completed": current_days >= target_days,
        "pct": min(100, round(current_days / target_days * 100, 1)) if target_days else 0,
        "unit": "days",
    }


async def _check_unique_contracts(db, wallet_id, task_config, params) -> Dict:
    """Count unique task_config_ids used (proxy for unique contract interactions)."""
    target = int(params.get("target_contracts", 5))
    result = await db.execute(
        select(func.count(distinct(Transaction.task_config_id))).where(
            Transaction.wallet_id == wallet_id,
            Transaction.status == "confirmed",
        )
    )
    current = result.scalar() or 0
    return {
        "metric": "achieve_unique_contracts",
        "current_value": current,
        "target": target,
        "completed": current >= target,
        "pct": min(100, round(current / target * 100, 1)) if target else 0,
    }


async def _check_unique_chains(db, wallet_id, task_config, params) -> Dict:
    """Count unique chains wallet has confirmed txs on."""
    target = int(params.get("target_chains", 3))
    result = await db.execute(
        select(func.count(distinct(Transaction.chain_id))).where(
            Transaction.wallet_id == wallet_id,
            Transaction.status == "confirmed",
        )
    )
    current = result.scalar() or 0
    return {
        "metric": "achieve_unique_chains",
        "current_value": current,
        "target": target,
        "completed": current >= target,
        "pct": min(100, round(current / target * 100, 1)) if target else 0,
    }


async def _check_balance(db, wallet_id, task_config, params) -> Dict:
    """Check if wallet holds minimum required token balance."""
    target_amount = float(params.get("target_balance", 0.0))
    token_symbol = params.get("token_symbol", "")
    result = await db.execute(
        select(WalletBalance).where(
            WalletBalance.wallet_id == wallet_id,
            WalletBalance.token_symbol == token_symbol,
        ).order_by(WalletBalance.last_updated.desc()).limit(1)
    )
    record = result.scalar_one_or_none()
    current = float(record.balance) if record else 0.0
    return {
        "metric": "maintain_balance",
        "current_value": current,
        "target": target_amount,
        "completed": current >= target_amount,
        "pct": min(100, round(current / target_amount * 100, 1)) if target_amount else 0,
        "token": token_symbol,
    }


async def is_metric_task(task_type: str) -> bool:
    return task_type in (
        "achieve_tx_count",
        "achieve_volume",
        "achieve_active_days",
        "achieve_unique_contracts",
        "achieve_unique_chains",
        "maintain_balance",
    )

