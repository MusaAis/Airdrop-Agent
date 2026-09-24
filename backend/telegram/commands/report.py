import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.reports.eligibility import get_eligibility_report
from backend.reports.roi import get_roi_report
from backend.reports.daily_progress import get_daily_progress_report
from backend.reports.activity import get_activity_log
from backend.reports.gas import get_gas_usage_report
from backend.reports.sybil import get_sybil_report
from backend.reports.server import get_server_status
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.report")

async def handle_report_eligibility(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    proj_id = int(args[0]) if args else None
    data = await get_eligibility_report(db, proj_id)
    return "\n".join(f"{r['wallet'][:10]}... – {r['project']}: {r['eligibility_pct']}%" for r in data)

async def handle_report_roi(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    proj_id = int(args[0]) if args else None
    data = await get_roi_report(db, proj_id)
    return "\n".join(f"{r['wallet'][:10]}... – {r['project']}: gas=${r['gas_spent_usd']} est=${r['estimated_token_value_usd']}" for r in data)

async def handle_report_daily_progress(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    proj_id = int(args[0]) if args else None
    data = await get_daily_progress_report(db, proj_id)
    return "\n".join(f"{r['wallet'][:10]}... – {r['task_type']}: {r['completed']}/{r['target']}" for r in data)

async def handle_report_gas(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    chain_id = int(args[0]) if args else None
    data = await get_gas_usage_report(db, chain_id)
    return "\n".join(f"{r['wallet'][:10]}... chain {r['chain']}: ${r['total_gas_usd']} ({r['tx_count']} tx)" for r in data)

async def handle_report_sybil(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    data = await get_sybil_report(db)
    return "\n".join(f"{r['wallet'][:10]}... risk:{r['risk_score']}" for r in data)

async def handle_report_activity(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    hours = int(args[0]) if args else 24
    logs = await get_activity_log(db, hours=hours)
    if not logs: return "No activity."
    return "\n".join(f"{l['created_at']} {l['wallet'][:8]} {l['task_type']} {l['status']}" for l in logs[:10])

async def handle_report_server(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    s = get_server_status()
    return f"RAM: {s['ram_percent']}% ({s['ram_used_gb']}/{s['ram_total_gb']} GB)\nCPU: {s['cpu_percent']}%\nDisk: {s['disk_percent']}% ({s['disk_free_gb']} GB free)\nWorkers: {s['worker_slots_active']}/{s['worker_slots_max']}"

async def handle_report_wallets(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from sqlalchemy import select as _s; from backend.models import Wallet
    wallets = (await db.execute(_s(Wallet))).scalars().all()
    if not wallets: return "No wallets."
    return "\n".join(f"W{w.id}: {w.address[:10]}… health:{w.health_score} sybil:{w.sybil_risk_score} fail:{w.failure_count} [{w.status}]" for w in wallets)

async def handle_report_weekly(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.reports.activity import get_activity_log
    from backend.reports.roi import get_roi_report
    logs = await get_activity_log(db, hours=168); roi = await get_roi_report(db, None)
    return f"📊 Weekly Summary\nTransactions: {len(logs)}\nProjects: {len({r['project'] for r in roi if 'project' in r})}\nGas spent: ${sum(r.get('gas_spent_usd',0) for r in roi):.2f}"

async def handle_report_snapshot(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from sqlalchemy import select as _s; from backend.models import Project; from datetime import date
    today = date.today()
    projects = (await db.execute(_s(Project).where(Project.airdrop_date != None).order_by(Project.airdrop_date.asc()))).scalars().all()
    if not projects: return "No snapshot deadlines configured."
    lines = ["📅 Snapshot Calendar:"]
    for p in projects:
        days = (p.airdrop_date - today).days
        flag = "🔴" if days <= 7 else "🟡" if days <= 30 else "🟢"
        lines.append(f"{flag} {p.name}: {p.airdrop_date} ({days}d)")
    return "\n".join(lines)

async def handle_report_failed(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from sqlalchemy import select as _s, func; from backend.models import Transaction
    from datetime import datetime, timedelta, timezone as _tz
    hours = int(args[0]) if args else 24
    since = datetime.now(_tz.utc) - timedelta(hours=hours)
    rows = (await db.execute(_s(Transaction.error_message, func.count(Transaction.id).label("cnt")).where(Transaction.status=="failed", Transaction.created_at>=since).group_by(Transaction.error_message).order_by(func.count(Transaction.id).desc()).limit(10))).all()
    if not rows: return f"No failed txs in last {hours}h."
    return f"Failed txs last {hours}h:\n" + "\n".join(f"  {r.cnt}× {(r.error_message or 'unknown')[:60]}" for r in rows)

async def handle_report_gas_estimate(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: report.gas_estimate <project_id>"
    from sqlalchemy import select as _s, func; from backend.models import TaskConfig, Wallet, Transaction
    from datetime import date; pid = int(args[0]); today = date.today().isoformat()
    tasks = (await db.execute(_s(TaskConfig).where(TaskConfig.project_id==pid, TaskConfig.enabled==True))).scalars().all()
    avg_gas = (await db.execute(_s(func.avg(Transaction.gas_cost_usd)).where(Transaction.gas_cost_usd!=None))).scalar() or 0.01
    wallets = (await db.execute(_s(Wallet).where(Wallet.status=="active"))).scalars().all()
    total_remaining = sum(t.daily_tx_min for t in tasks) * len(wallets)
    return f"Estimate for project {pid}: ~{total_remaining} txs × ${avg_gas:.4f} = ${total_remaining*avg_gas:.2f}"

async def handle_report_compare(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 2: return "Usage: report.compare <wallet_id1> <wallet_id2>"
    from sqlalchemy import select as _s, func; from backend.models import Wallet, Transaction
    w1 = await db.get(Wallet, int(args[0])); w2 = await db.get(Wallet, int(args[1]))
    if not w1 or not w2: return "Wallet not found."
    async def stats(wid):
        cnt = (await db.execute(_s(func.count(Transaction.id)).where(Transaction.wallet_id==wid))).scalar() or 0
        gas = (await db.execute(_s(func.sum(Transaction.gas_cost_usd)).where(Transaction.wallet_id==wid))).scalar() or 0
        fail= (await db.execute(_s(func.count(Transaction.id)).where(Transaction.wallet_id==wid,Transaction.status=="failed"))).scalar() or 0
        return cnt,gas,fail
    c1,g1,f1 = await stats(w1.id); c2,g2,f2 = await stats(w2.id)
    return f"Wallet {w1.id} vs {w2.id}\nTxs: {c1} vs {c2}\nGas$: {g1:.2f} vs {g2:.2f}\nFailed: {f1} vs {f2}\nHealth: {w1.health_score} vs {w2.health_score}"

async def handle_report_project(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: report.project <id>"
    from backend.projects.manager import get_project
    from backend.reports.eligibility import get_eligibility_report
    pid = int(args[0]); project = await get_project(db, pid)
    if not project: return "Project not found."
    elig = await get_eligibility_report(db, pid)
    avg = (sum(r.get("eligibility_pct",0) for r in elig)/len(elig)) if elig else 0
    return f"📋 {project.name}\nStatus: {project.status}  Priority: {project.priority}\nCircuit: {'🔴 ACTIVE' if project.circuit_breaker_active else '🟢 OK'}\nAvg eligibility: {avg:.0f}%\nWallets: {len(elig)}"
