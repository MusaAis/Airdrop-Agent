import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import CompetitorWallet
from backend.telegram.whitelist import is_whitelisted

async def handle_competitor_add(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 1: return "Usage: competitor.add <address> [label]"
    addr = args[0]
    label = args[1] if len(args) > 1 else None
    existing = (await db.execute(select(CompetitorWallet).where(CompetitorWallet.address == addr))).scalar_one_or_none()
    if existing: return "Wallet already tracked."
    db.add(CompetitorWallet(address=addr, label=label))
    await db.commit()
    return f"Competitor wallet {addr} added."

async def handle_competitor_list(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    wallets = (await db.execute(select(CompetitorWallet))).scalars().all()
    if not wallets: return "No tracked wallets."
    return "\n".join(f"{w.address[:10]}... label:{w.label}" for w in wallets)

async def handle_competitor_analyze(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: competitor.analyze <address>"
    addr = args[0]
    # Dummy analysis: just mark last_analyzed
    wallet = (await db.execute(select(CompetitorWallet).where(CompetitorWallet.address == addr))).scalar_one_or_none()
    if not wallet: return "Wallet not tracked."
    wallet.last_analyzed = datetime.utcnow()
    await db.commit()
    return f"Analysis for {addr} updated (patterns not yet extracted)."
