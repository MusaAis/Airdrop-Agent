import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Wallet, WalletBalance, WalletNonce
from backend.wallet.manager import (
    create_hd_wallets, list_wallets, get_wallet, pause_wallet, resume_wallet,
    blacklist_wallet, set_gas_wallet_flag, get_wallet_settings, update_wallet_settings
)
from backend.chains.manager import get_chain
from backend.telegram.whitelist import is_whitelisted
from backend.faucet.manager import auto_gas_refill

logger = logging.getLogger("airdrop.tg.wallet")

async def _resolve_wallet(identifier: str, db: AsyncSession):
    try: return await db.get(Wallet, int(identifier))
    except ValueError:
        r = await db.execute(select(Wallet).where(Wallet.address == identifier))
        return r.scalar_one_or_none()

async def handle_wallet_create(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    count = int(args[0]) if args else 1
    wallets = await create_hd_wallets(db, count)
    return "✅ Created:\n" + "\n".join(f"• {w.address} (ID {w.id})" for w in wallets)

async def handle_wallet_list(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    wallets = await list_wallets(db)
    if not wallets: return "No wallets."
    return "\n".join(f"{w.id}: {w.address[:10]}... [{w.status}]" for w in wallets)

async def handle_wallet_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.status <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    bal = (await db.execute(select(WalletBalance).where(WalletBalance.wallet_id==wallet.id))).scalars().all()
    bal_str = "\n".join(f"  Chain {b.chain_id}: {b.token_symbol} {b.balance}" for b in bal) or "No balances"
    return (f"ID {wallet.id}: {wallet.address}\nStatus: {wallet.status}\nGas wallet: {wallet.is_gas_wallet}\n"
            f"Health: {wallet.health_score}\nSybil: {wallet.sybil_risk_score}\nFailures: {wallet.failure_count}\nBalances:\n{bal_str}")

async def handle_wallet_balance(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.balance <id/all>"
    target = args[0].lower()
    wallets = []
    if target == "all":
        wallets = await list_wallets(db)
    else:
        w = await _resolve_wallet(args[0], db)
        if w: wallets.append(w)
    if not wallets: return "No wallets."
    lines = []
    for w in wallets:
        bal = (await db.execute(select(WalletBalance).where(WalletBalance.wallet_id==w.id))).scalars().all()
        lines.append(f"{w.id}: {w.address[:10]}...")
        if bal:
            for b in bal:
                lines.append(f"  {b.token_symbol}: {b.balance} (~${b.usd_value})")
        else:
            lines.append("  No data")
    return "\n".join(lines)

async def handle_wallet_pause(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.pause <id/all>"
    if args[0].lower()=="all":
        if confirmation is None: return "⚠️ Confirm pause all wallets? Reply 'confirm'"
        wallets = await list_wallets(db)
        for w in wallets: await pause_wallet(db, w.id)
        return "⏸ All paused."
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    if confirmation is None: return f"⚠️ Confirm pause wallet {wallet.id}? Reply 'confirm'"
    await pause_wallet(db, wallet.id)
    return f"⏸ Wallet {wallet.id} paused."

async def handle_wallet_resume(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.resume <id/all>"
    if args[0].lower()=="all":
        wallets = await list_wallets(db)
        for w in wallets: await resume_wallet(db, w.id)
        return "▶ All resumed."
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    await resume_wallet(db, wallet.id)
    return f"▶ Wallet {wallet.id} resumed."

async def handle_wallet_cooldown(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: wallet.cooldown <id> <hours>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    if confirmation is None: return f"⚠️ Confirm cooldown {args[1]}h for wallet {wallet.id}? Reply 'confirm'"
    wallet.status = "cooldown"
    await db.commit()
    return f"✅ Cooldown set."

async def handle_wallet_blacklist(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.blacklist <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    if confirmation is None: return f"⚠️ BLACKLIST wallet {wallet.id}? Reply 'confirm'"
    await blacklist_wallet(db, wallet.id)
    return f"🛑 Blacklisted."

async def handle_wallet_unblacklist(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.unblacklist <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    wallet.status = "active"
    await db.commit()
    return "✅ Restored."

async def handle_wallet_archive(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.archive <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    if confirmation is None: return f"⚠️ Archive wallet {wallet.id}? Reply 'confirm'"
    wallet.status = "archived"
    await db.commit()
    return "📦 Archived."

async def handle_wallet_unarchive(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.unarchive <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    wallet.status = "active"
    await db.commit()
    return "✅ Unarchived."

async def handle_wallet_tag(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: wallet.tag <id> <tag>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    tags = wallet.tags or []
    if args[1] not in tags: tags.append(args[1])
    wallet.tags = tags
    await db.commit()
    return f"Tag '{args[1]}' added."

async def handle_wallet_untag(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: wallet.untag <id> <tag>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    tags = wallet.tags or []
    if args[1] in tags: tags.remove(args[1])
    wallet.tags = tags
    await db.commit()
    return "Tag removed."

async def handle_wallet_group(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.group <tag>"
    wallets = (await db.execute(select(Wallet).where(Wallet.tags.contains(args[0])))).scalars().all()
    return "\n".join(f"{w.id}: {w.address[:10]}" for w in wallets) if wallets else "No wallets found."

async def handle_wallet_fund(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: wallet.fund <wallet_id> <chain_id>"
    wallet = await _resolve_wallet(args[0], db)
    chain = await get_chain(db, int(args[1]))
    if not wallet or not chain: return "Wallet/chain not found."
    await auto_gas_refill(wallet, chain, db)
    return "Gas refill triggered."

async def handle_wallet_health(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.health <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    return f"Wallet {wallet.id}: Health={wallet.health_score}/100, Sybil={wallet.sybil_risk_score}"

async def handle_wallet_sybil(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.sybil <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    return f"Wallet {wallet.id} Sybil Risk: {wallet.sybil_risk_score}"

async def handle_wallet_persona(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.persona <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    settings = await get_wallet_settings(db, wallet.id)
    if not settings: return "No settings."
    return (f"Persona for wallet {wallet.id}:\nActive hours: {settings.active_hour_start}-{settings.active_hour_end}\n"
            f"Sleep: {settings.sleep_min_mins}-{settings.sleep_max_mins} min\nGas mult: {settings.gas_multiplier}\n"
            f"Amount distribution: {settings.amount_distribution}\nBidirectional default: {settings.bidirectional_default}\n"
            f"Daily TX range: {settings.daily_tx_min}-{settings.daily_tx_max}")

async def handle_wallet_top(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    n = int(args[0]) if args else 5
    wallets = (await db.execute(select(Wallet).order_by(Wallet.health_score.desc()).limit(n))).scalars().all()
    return "\n".join(f"{w.id}: {w.address[:10]}... Health:{w.health_score}" for w in wallets)

async def handle_wallet_failing(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    wallets = (await db.execute(select(Wallet).where(Wallet.failure_count>0))).scalars().all()
    return "\n".join(f"{w.id}: {w.address[:10]}... failures:{w.failure_count}" for w in wallets) if wallets else "No failing wallets."

async def handle_wallet_gas_wallets(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    wallets = (await db.execute(select(Wallet).where(Wallet.is_gas_wallet==True))).scalars().all()
    return "\n".join(f"{w.id}: {w.address[:10]}" for w in wallets) if wallets else "No gas wallets."

async def handle_wallet_set_gas(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: wallet.set_gas <id> <true/false>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    await set_gas_wallet_flag(db, wallet.id, args[1].lower()=="true")
    return f"Gas wallet flag set to {args[1]}."

async def handle_wallet_nonce(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: wallet.nonce <wallet_id> <chain_id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    nonce = (await db.execute(select(WalletNonce).where(WalletNonce.wallet_id==wallet.id, WalletNonce.chain_id==int(args[1])))).scalar_one_or_none()
    if not nonce: return "No nonce record."
    return f"Nonce: {nonce.nonce} (locked: {nonce.locked})"

async def handle_wallet_warmup(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: wallet.warmup <id>"
    wallet = await _resolve_wallet(args[0], db)
    if not wallet: return "Wallet not found."
    if wallet.warmup_complete: return f"Wallet {wallet.id} warmup already complete."
    import asyncio; from backend.wallet.warmup import run_warmup; from backend.chains.manager import list_chains
    chains = await list_chains(db)
    if not chains: return "No chains configured."
    asyncio.create_task(run_warmup(wallet, chains[0], db))
    return f"🔥 Warmup started for wallet {wallet.id} on {chains[0].name}."
