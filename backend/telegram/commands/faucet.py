import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Faucet, Wallet, Chain
from backend.faucet.manager import request_faucet_for_wallet
from backend.wallet.manager import get_wallet
from backend.chains.manager import get_chain
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.faucet")

async def handle_faucet_list(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from sqlalchemy import select
    faucets = (await db.execute(select(Faucet))).scalars().all()
    if not faucets: return "No faucets."
    return "\n".join(f"{f.id}: {f.name} (chain:{f.chain_id}) cooldown:{f.cooldown_hours}h" for f in faucets)

async def handle_faucet_request(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: faucet.request <wallet_id> <chain_id>"
    wallet = await get_wallet(db, int(args[0]))
    chain = await get_chain(db, int(args[1]))
    if not wallet or not chain: return "Wallet/chain not found."
    result = await request_faucet_for_wallet(wallet, chain, db)
    return f"Faucet result: {result}"

async def handle_faucet_bulk(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    # Trigger for all active wallets on a chain
    if not args: return "Usage: faucet.bulk <chain_id>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    from backend.wallet.manager import list_wallets
    wallets = await list_wallets(db, status_filter="active")
    results = []
    for w in wallets:
        r = await request_faucet_for_wallet(w, chain, db)
        results.append(f"Wallet {w.id}: {r}")
    return "\n".join(results)

async def handle_faucet_add(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 3: return "Usage: faucet.add <chain_id> <url> <cooldown_hours>"
    faucet = Faucet(chain_id=int(args[0]), name=f"Faucet-{args[0]}", url=args[1], cooldown_hours=int(args[2]), enabled=True)
    db.add(faucet); await db.commit(); await db.refresh(faucet)
    return f"✅ Faucet added (ID:{faucet.id})."

async def handle_faucet_add_fallback(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 2: return "Usage: faucet.add_fallback <faucet_id> <url>"
    faucet = await db.get(Faucet, int(args[0]))
    if not faucet: return "Faucet not found."
    faucet.fallback_urls = list(faucet.fallback_urls or []) + [args[1]]
    await db.commit(); return f"✅ Fallback added to faucet {faucet.id}."

async def handle_faucet_enable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    faucet = await db.get(Faucet, int(args[0])) if args else None
    if not faucet: return "Faucet not found."
    faucet.enabled = True; await db.commit(); return f"✅ Faucet {faucet.id} enabled."

async def handle_faucet_disable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    faucet = await db.get(Faucet, int(args[0])) if args else None
    if not faucet: return "Faucet not found."
    faucet.enabled = False; await db.commit(); return f"⏸ Faucet {faucet.id} disabled."

async def handle_faucet_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: faucet.status <wallet_id>"
    from sqlalchemy import select as _s; from backend.models import FaucetRequest
    rows = (await db.execute(_s(FaucetRequest).where(FaucetRequest.wallet_id==int(args[0])).order_by(FaucetRequest.requested_at.desc()).limit(10))).scalars().all()
    if not rows: return "No faucet history."
    return "\n".join(f"F{r.faucet_id}: {r.status} at {r.requested_at.strftime('%m-%d %H:%M')}" for r in rows)

async def handle_faucet_history(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from sqlalchemy import select as _s; from backend.models import FaucetRequest
    wid = int(args[0]) if args else None
    stmt = _s(FaucetRequest).order_by(FaucetRequest.requested_at.desc()).limit(20)
    if wid: stmt = stmt.where(FaucetRequest.wallet_id==wid)
    rows = (await db.execute(stmt)).scalars().all()
    if not rows: return "No faucet history."
    return "\n".join(f"W{r.wallet_id} F{r.faucet_id}: {r.status} {r.requested_at.strftime('%m-%d %H:%M')}" for r in rows)
