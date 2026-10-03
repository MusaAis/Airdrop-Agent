"""
Factual gas reporting in the chain's own gas token (ROADMAP item 3).

gas_cost_usd prices a testnet token at its MAINNET value, which is meaningless, and it is empty
whenever the price lookup fails. gas_cost_native (fee actually paid, in gas-token units) is always
recorded. Totals are kept PER TOKEN because adding ETH to BNB is not a number.

"Gas spent" here counts every transaction that has a recorded fee, including ones that reverted
on-chain (a revert still burns gas). Transactions recorded before fee tracking existed have no fee
and are simply not counted.
"""
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Transaction, TaskConfig


async def gas_native_totals(
    db: AsyncSession,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    wallet_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> Dict[str, float]:
    """{gas token symbol: total fee paid} for the given filters."""
    stmt = (
        select(Transaction.gas_token, func.sum(Transaction.gas_cost_native))
        .where(Transaction.gas_cost_native.is_not(None))
        .group_by(Transaction.gas_token)
    )
    if since is not None:
        stmt = stmt.where(Transaction.created_at >= since)
    if until is not None:
        stmt = stmt.where(Transaction.created_at < until)
    if wallet_id is not None:
        stmt = stmt.where(Transaction.wallet_id == wallet_id)
    if project_id is not None:
        stmt = stmt.join(TaskConfig, Transaction.task_config_id == TaskConfig.id).where(
            TaskConfig.project_id == project_id)
    rows = (await db.execute(stmt)).all()
    return {(sym or "?"): float(total or 0.0) for sym, total in rows if total}


def merge_totals(*parts: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for p in parts:
        for k, v in (p or {}).items():
            out[k] = out.get(k, 0.0) + v
    return out


def format_gas_native(totals: Dict[str, float]) -> str:
    """'0.00123 ETH · 0.0004 BNB', largest first; 'none recorded' when empty."""
    if not totals:
        return "none recorded"
    parts = sorted(totals.items(), key=lambda kv: -kv[1])
    return " · ".join(f"{v:.6g} {sym}" for sym, v in parts)
