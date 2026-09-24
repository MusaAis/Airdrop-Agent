import logging
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.claim")


async def handle_claim_check(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import Wallet, Project, TaskDailyProgress
    from sqlalchemy import select
    from datetime import datetime, timezone
    wallets = (await db.execute(select(Wallet).where(Wallet.status == "active"))).scalars().all()
    projects = (await db.execute(select(Project).where(Project.status == "active"))).scalars().all()
    if not wallets or not projects:
        return "No active wallets or projects to check."
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"💰 Claim Scan — {today}"]
    for p in projects:
        if p.airdrop_date:
            lines.append(f"\n📋 {p.name}: TGE {p.airdrop_date}")
            for w in wallets[:5]:  # show first 5
                lines.append(f"  wallet#{w.id}: {w.address[:10]}... — manual check required")
    if len(lines) == 1:
        lines.append("No projects with known airdrop dates.\nAdd airdrop_date to projects to track claims.")
    lines.append("\n💡 Claim automation requires contract addresses in Project → Contracts.")
    return "\n".join(lines)


async def handle_claim_eligible(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import Wallet, Project
    from sqlalchemy import select
    wallets = (await db.execute(select(Wallet).where(Wallet.status == "active"))).scalars().all()
    projects = (await db.execute(select(Project).where(Project.airdrop_date != None))).scalars().all()
    if not projects:
        return "No projects with airdrop dates set.\nUse /project_add and set airdrop_date."
    lines = [f"💰 Eligible Wallets by Project:"]
    for p in projects:
        lines.append(f"\n{p.name} (TGE: {p.airdrop_date}):")
        for w in wallets:
            lines.append(f"  wallet#{w.id}: {w.address[:12]}...")
    return "\n".join(lines)


async def handle_claim_value(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    pid = int(args[0]) if args else None
    from backend.models import Project
    from sqlalchemy import select
    if pid:
        project = await db.get(Project, pid)
        if not project: return f"Project {pid} not found."
        projects = [project]
    else:
        projects = (await db.execute(select(Project).where(Project.status == "active"))).scalars().all()
    lines = ["💰 Estimated Claim Values (requires manual verification):"]
    for p in projects:
        lines.append(f"\n{p.name}: ROI estimation requires AI analysis — use /ai_validate {p.id}")
    return "\n".join(lines)


async def handle_claim_trigger(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 2: return "Usage: /claim_trigger <wallet_id> <project_id>"
    return (
        "⚠️ Manual claim trigger requires:\n"
        "1. Claim contract address added in Project → Contracts\n"
        "2. Claim ABI configured\n"
        "3. Wallet has claimable tokens\n\n"
        "Add the claim contract via /project_add and configure via dashboard."
    )


async def handle_claim_set_threshold(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: /claim_set_threshold <usd>"
    try:
        threshold = float(args[0])
        from backend.models import Project
        from sqlalchemy import select, update
        await db.execute(update(Project).values(auto_claim_threshold_usd=threshold))
        await db.commit()
        return f"✅ Auto-claim threshold set to ${threshold:.2f} for all projects."
    except Exception as e:
        return f"❌ Error: {e}"


async def handle_claim_auto_on(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    return "✅ Auto-claim enabled. Claims below threshold will execute automatically when claim contracts are configured."


async def handle_claim_auto_off(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    return "✅ Auto-claim disabled. All claims will require manual approval."


async def handle_claim_pending(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import Project
    from sqlalchemy import select
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    projects = (await db.execute(
        select(Project).where(Project.airdrop_date != None, Project.status == "active")
    )).scalars().all()
    upcoming = [p for p in projects if p.airdrop_date and p.airdrop_date >= today]
    if not upcoming:
        return "No pending claims with known airdrop dates."
    lines = ["💰 Pending Claims:"]
    for p in sorted(upcoming, key=lambda x: x.airdrop_date):
        days = (p.airdrop_date - today).days
        lines.append(f"• {p.name}: TGE in {days} days ({p.airdrop_date}) — threshold ${p.auto_claim_threshold_usd:.0f}")
    return "\n".join(lines)


async def handle_claim_history(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import Transaction
    from sqlalchemy import select, desc
    # Look for transactions that might be claims
    txs = (await db.execute(
        select(Transaction).where(Transaction.status == "confirmed").order_by(desc(Transaction.confirmed_at)).limit(20)
    )).scalars().all()
    if not txs:
        return "No confirmed transactions found."
    lines = ["💰 Recent Confirmed Transactions (potential claims):"]
    for tx in txs:
        lines.append(f"wallet#{tx.wallet_id}: {tx.tx_hash[:16]}... | gas ${tx.gas_cost_usd or 0:.4f}")
    return "\n".join(lines)
