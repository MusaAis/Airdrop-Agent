import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Wallet, Transaction, TaskConfig

logger = logging.getLogger("airdrop.sybil")


async def compute_wallet_correlations(db: AsyncSession) -> List[Dict]:
    """
    Detect Sybil patterns across wallets.
    Checks: timing correlation and task sequence similarity.
    Returns list of suspicious wallet pairs with scores.
    """
    wallets_result = await db.execute(
        select(Wallet).where(Wallet.status.in_(["active", "paused"]))
    )
    wallets = wallets_result.scalars().all()
    if len(wallets) < 2:
        return []

    # Fetch recent transactions for all wallets (last 30 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    txs_result = await db.execute(
        select(Transaction).where(
            Transaction.created_at >= cutoff,
            Transaction.status == "confirmed",
        )
    )
    txs = txs_result.scalars().all()

    # Group by wallet
    wallet_txs: Dict[int, List[Transaction]] = defaultdict(list)
    for tx in txs:
        wallet_txs[tx.wallet_id].append(tx)

    suspicious_pairs = []
    wallet_list = [w for w in wallets if wallet_txs.get(w.id)]
    n = len(wallet_list)

    for i in range(n):
        for j in range(i + 1, n):
            wa = wallet_list[i]
            wb = wallet_list[j]
            score, evidence = _compare_wallets(
                wa, wallet_txs[wa.id], wb, wallet_txs[wb.id]
            )
            if score >= 20:
                suspicious_pairs.append({
                    "wallet_a": wa.id,
                    "wallet_b": wb.id,
                    "correlation_score": score,
                    "risk_level": _score_to_level(score),
                    "evidence": evidence,
                    "recommendation": _recommendation(score),
                })

    # Update sybil_risk_score on wallet models
    wallet_max_score: Dict[int, int] = defaultdict(int)
    for pair in suspicious_pairs:
        wallet_max_score[pair["wallet_a"]] = max(
            wallet_max_score[pair["wallet_a"]], pair["correlation_score"]
        )
        wallet_max_score[pair["wallet_b"]] = max(
            wallet_max_score[pair["wallet_b"]], pair["correlation_score"]
        )

    for w in wallets:
        if w.id in wallet_max_score:
            w.sybil_risk_score = wallet_max_score[w.id]
    await db.commit()

    return suspicious_pairs


def _compare_wallets(
    wa: "Wallet", txs_a: List["Transaction"],
    wb: "Wallet", txs_b: List["Transaction"],
) -> tuple:
    evidence = []
    total_score = 0

    # 1. Timing correlation — transactions within 10 minutes of each other
    times_a = sorted(tx.created_at for tx in txs_a if tx.created_at)
    times_b = sorted(tx.created_at for tx in txs_b if tx.created_at)
    close_pairs = 0
    for ta in times_a:
        for tb in times_b:
            diff = abs((ta - tb).total_seconds())
            if diff <= 600:  # 10 minutes
                close_pairs += 1
    if close_pairs >= 3:
        timing_score = min(40, close_pairs * 5)
        total_score += timing_score
        evidence.append({
            "dimension": "timing",
            "finding": f"{close_pairs} transactions within 10 min of each other",
            "severity": "high" if close_pairs >= 5 else "medium",
        })

    # 2. Task config sequence similarity
    tasks_a = [tx.task_config_id for tx in txs_a if tx.task_config_id]
    tasks_b = [tx.task_config_id for tx in txs_b if tx.task_config_id]
    if tasks_a and tasks_b:
        set_a = set(tasks_a)
        set_b = set(tasks_b)
        overlap = len(set_a & set_b)
        union = len(set_a | set_b)
        if union > 0:
            similarity = overlap / union
            if similarity > 0.8:
                seq_score = int(similarity * 30)
                total_score += seq_score
                evidence.append({
                    "dimension": "task_sequence",
                    "finding": f"{int(similarity*100)}% task overlap between wallets",
                    "severity": "medium",
                })

    # 3. Gas price similarity (same gasPrice used repeatedly)
    gas_prices_a = set(tx.gas_price for tx in txs_a if tx.gas_price)
    gas_prices_b = set(tx.gas_price for tx in txs_b if tx.gas_price)
    gas_overlap = gas_prices_a & gas_prices_b
    if len(gas_overlap) >= 2:
        total_score += 15
        evidence.append({
            "dimension": "gas_price",
            "finding": f"{len(gas_overlap)} identical gas prices used by both wallets",
            "severity": "low",
        })

    return min(100, total_score), evidence


def _score_to_level(score: int) -> str:
    if score >= 80:
        return "critical"
    elif score >= 60:
        return "high"
    elif score >= 40:
        return "medium"
    return "low"


def _recommendation(score: int) -> str:
    if score >= 80:
        return "Immediately stagger these wallets — critical Sybil risk"
    elif score >= 60:
        return "Change active hours and amount ranges for one of these wallets"
    elif score >= 40:
        return "Monitor — increase start offset and diversify task timing"
    return "Low risk — continue monitoring"
