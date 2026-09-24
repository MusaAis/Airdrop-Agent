import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend.database import async_session
from backend.models import Transaction, RPCLog
from backend.agent import worker_pool

async def get_avg_confirmation_time(chain_id: int, hours: int = 24) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with async_session() as db:
        txs = (await db.execute(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                Transaction.created_at >= since,
                Transaction.status == "confirmed",
                Transaction.confirmed_at != None
            )
        )).scalars().all()
        if not txs:
            return {"chain_id": chain_id, "avg_seconds": None, "count": 0}
        total = sum((tx.confirmed_at - tx.created_at).total_seconds() for tx in txs)
        return {"chain_id": chain_id, "avg_seconds": round(total / len(txs), 1), "count": len(txs)}

async def get_worker_utilization() -> dict:
    total = worker_pool.max_slots
    active = sum(1 for s in worker_pool.slots if s is not None)
    return {
        "total_slots": total,
        "active_slots": active,
        "utilization_pct": round(active / total * 100, 1) if total else 0,
        "slot_details": [{"slot": i, "active": bool(s)} for i, s in enumerate(worker_pool.slots)]
    }

async def get_rpc_latency_percentiles(chain_id: int) -> dict:
    async with async_session() as db:
        logs = (await db.execute(
            select(RPCLog.latency_ms).where(
                RPCLog.chain_id == chain_id,
                RPCLog.latency_ms != None
            ).order_by(RPCLog.latency_ms)
        )).scalars().all()
        if not logs:
            return {"chain_id": chain_id, "p50": None, "p95": None, "p99": None}
        sorted_logs = sorted(logs)
        n = len(sorted_logs)
        def percentile(p):
            idx = int(n * p / 100)
            return sorted_logs[idx] if idx < n else sorted_logs[-1]
        return {"chain_id": chain_id, "p50_ms": percentile(50), "p95_ms": percentile(95), "p99_ms": percentile(99), "sample_count": n}
