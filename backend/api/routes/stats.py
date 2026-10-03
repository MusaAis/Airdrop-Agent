"""
Stats overview (the dashboard tab deferred from Phase 4, built in Phase 7).
Read-only: totals, project/wallet breakdowns and per-project rollups computed
from data that already exists (transactions, task configs, project columns).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.security.auth import verify_token
from backend.models import Project, Wallet, TaskConfig, Transaction, Alert

from backend.reports.gas_native import gas_native_totals, format_gas_native

router = APIRouter(prefix="/stats", tags=["stats"])


def _count_if(cond):
    return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)


async def _tx_stats(db: AsyncSession, since=None) -> dict:
    stmt = select(
        func.count(Transaction.id),
        _count_if(Transaction.status == "confirmed"),
        _count_if(Transaction.status == "failed"),
        func.coalesce(func.sum(case((Transaction.status == "confirmed", Transaction.gas_cost_usd), else_=0)), 0),
    )
    if since is not None:
        stmt = stmt.where(Transaction.created_at >= since)
    total, ok, failed, gas = (await db.execute(stmt)).one()
    ok, failed = int(ok or 0), int(failed or 0)
    native = await gas_native_totals(db, since=since)
    return {
        "total": int(total or 0), "confirmed": ok, "failed": failed,
        "gas_usd": round(float(gas or 0), 2),
        # factual per-token gas (USD above is an estimate and meaningless on testnets)
        "gas_native": {k: round(v, 8) for k, v in native.items()},
        "gas_native_text": format_gas_native(native),
        "success_rate": round(ok / (ok + failed) * 100, 1) if (ok + failed) else None,
    }


@router.get("/overview")
async def overview(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc).replace(tzinfo=None)   # DB stores naive UTC

    # ── projects ──
    projects = (await db.execute(select(Project))).scalars().all()
    by_status, by_elig = {}, {}
    est_value = 0.0
    for p in projects:
        by_status[p.status] = by_status.get(p.status, 0) + 1
        e = p.eligibility_status or "pending"
        by_elig[e] = by_elig.get(e, 0) + 1
        if e == "eligible":
            est_value += float(p.eligibility_value_usd or 0)

    # ── wallets ──
    w_rows = (await db.execute(select(Wallet.status, func.count()).group_by(Wallet.status))).all()
    gas_wallets = (await db.execute(
        select(func.count()).select_from(Wallet).where(Wallet.is_gas_wallet == True)
    )).scalar() or 0

    # ── per-project rollups ──
    task_rows = {
        pid: (total, enabled) for pid, total, enabled in (await db.execute(
            select(TaskConfig.project_id, func.count(TaskConfig.id), _count_if(TaskConfig.enabled == True))
            .group_by(TaskConfig.project_id)
        )).all()
    }
    tx_rows = {
        r[0]: r for r in (await db.execute(
            select(
                TaskConfig.project_id,
                func.count(Transaction.id),
                _count_if(Transaction.status == "confirmed"),
                _count_if(Transaction.status == "failed"),
                func.coalesce(func.sum(case((Transaction.status == "confirmed", Transaction.gas_cost_usd), else_=0)), 0),
                func.count(func.distinct(Transaction.wallet_id)),
                func.count(func.distinct(func.date(Transaction.confirmed_at))),
                func.max(Transaction.created_at),
            )
            .select_from(Transaction)
            .join(TaskConfig, Transaction.task_config_id == TaskConfig.id)
            .group_by(TaskConfig.project_id)
        )).all()
    }
    native_rows = (await db.execute(
        select(TaskConfig.project_id, Transaction.gas_token, func.sum(Transaction.gas_cost_native))
        .select_from(Transaction)
        .join(TaskConfig, Transaction.task_config_id == TaskConfig.id)
        .where(Transaction.gas_cost_native.is_not(None))
        .group_by(TaskConfig.project_id, Transaction.gas_token)
    )).all()
    native_by_project: dict = {}
    for pid, sym, total in native_rows:
        if total:
            native_by_project.setdefault(pid, {})[sym or "?"] = float(total)
    per_project = []
    for p in projects:
        t_total, t_enabled = task_rows.get(p.id, (0, 0))
        r = tx_rows.get(p.id)
        per_project.append({
            "id": p.id, "name": p.name, "status": p.status, "priority": p.priority,
            "eligibility_status": p.eligibility_status or "pending",
            "eligibility_value_usd": p.eligibility_value_usd,
            "tasks_total": int(t_total or 0), "tasks_enabled": int(t_enabled or 0),
            "tx_total": int(r[1]) if r else 0,
            "tx_confirmed": int(r[2]) if r else 0,
            "tx_failed": int(r[3]) if r else 0,
            "gas_usd": round(float(r[4] or 0), 2) if r else 0.0,
            "gas_native": {k: round(v, 8) for k, v in native_by_project.get(p.id, {}).items()},
            "gas_native_text": format_gas_native(native_by_project.get(p.id, {})),
            "wallets": int(r[5]) if r else 0,
            "active_days": int(r[6]) if r else 0,
            "last_tx_at": r[7].isoformat() if r and r[7] else None,
        })
    per_project.sort(key=lambda x: (x["status"] == "archived", -x["tx_total"]))

    alerts_unresolved = (await db.execute(
        select(func.count()).select_from(Alert).where(Alert.resolved == False)
    )).scalar() or 0

    ai = None
    try:
        from backend.core.autonomy import autonomy_summary
        ai = await autonomy_summary(db)
    except Exception:
        pass

    return {
        "projects": {"total": len(projects), "by_status": by_status, "by_eligibility": by_elig,
                     "estimated_value_usd": round(est_value, 2)},
        "wallets": {"total": sum(n for _, n in w_rows), "by_status": {s: n for s, n in w_rows},
                    "gas_wallets": int(gas_wallets)},
        "transactions": {
            "all_time": await _tx_stats(db),
            "last_7d": await _tx_stats(db, now - timedelta(days=7)),
            "last_24h": await _tx_stats(db, now - timedelta(hours=24)),
        },
        "per_project": per_project,
        "alerts_unresolved": int(alerts_unresolved),
        "ai": ai,
    }
