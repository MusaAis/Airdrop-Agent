import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.chains.gas import get_current_gas_price, get_6h_average_gas
from backend.chains.rpc_pool import get_web3
from backend.chains.manager import get_chain
from backend.telegram.whitelist import is_whitelisted

async def handle_gas_price(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: gas.price <chain_id>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    w3 = await get_web3(chain)
    price = await get_current_gas_price(w3)
    return f"Gas price on {chain.name}: {price} wei"

async def handle_gas_spike(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: gas.spike <chain_id>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    w3 = await get_web3(chain)
    current = await get_current_gas_price(w3)
    avg = await get_6h_average_gas(chain.id, w3)
    spike = current > avg * 3
    return f"Chain {chain.name}: current {current}, 6h avg {avg}, spike: {spike}"

async def handle_gas_optimal(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: gas.optimal <chain_id>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    w3 = await get_web3(chain)
    current = await get_current_gas_price(w3)
    avg = await get_6h_average_gas(chain.id, w3)
    if current < avg * 0.9:
        return f"Current gas ({current}) is below 6h average ({avg}). Good time to transact."
    elif current > avg * 1.5:
        return f"Current gas ({current}) is significantly above average ({avg}). Consider waiting."
    else:
        return f"Current gas ({current}) is near average ({avg}). Normal conditions."

async def handle_gas_cost(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args) < 1: return "Usage: gas.cost <wallet_id> [hours]"
    wid = int(args[0])
    hours = int(args[1]) if len(args)>1 else 24
    from backend.models import Transaction
    from sqlalchemy import select, func
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    from backend.reports.gas_native import gas_native_totals, format_gas_native
    total = await gas_native_totals(db, since=since, wallet_id=wid)
    return f"Total gas spent by wallet {wid} in last {hours}h: {format_gas_native(total)}"

async def handle_gas_budget(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: gas.budget <wallet_id> <usd_per_day>"
    wid = int(args[0])
    budget = float(args[1])
    from backend.wallet.manager import update_wallet_settings
    # Store budget in wallet settings (using a custom field – we'll store in persona for now)
    # For simplicity, we'll just set a note in wallet persona
    wallet = await db.get(Wallet, wid)  # need import
    from backend.models import Wallet
    wallet = await db.get(Wallet, wid)
    if not wallet: return "Wallet not found."
    persona = wallet.persona or {}
    persona["gas_budget_usd"] = budget
    wallet.persona = persona
    await db.commit()
    return f"Daily gas budget set to ${budget} for wallet {wid}."

async def handle_gas_refill(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: gas.refill <wallet_id> <chain_id>"
    wid = int(args[0])
    cid = int(args[1])
    from backend.faucet.manager import auto_gas_refill
    from backend.wallet.manager import get_wallet
    wallet = await get_wallet(db, wid)
    chain = await get_chain(db, cid)
    if not wallet or not chain: return "Wallet/chain not found."
    await auto_gas_refill(wallet, chain, db)
    return "Gas refill triggered."

async def handle_gas_history(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: gas.history <chain_id>"
    from sqlalchemy import select as _s; from backend.models import RpcRequestLog
    from datetime import datetime, timedelta, timezone as _tz
    rows = (await db.execute(_s(RpcRequestLog).where(RpcRequestLog.chain_id==int(args[0]),RpcRequestLog.created_at>=datetime.now(_tz.utc)-timedelta(hours=24)).order_by(RpcRequestLog.created_at.desc()).limit(20))).scalars().all()
    if not rows: return f"No RPC history for chain {args[0]}."
    return "\n".join(f"{r.created_at.strftime('%H:%M')} {r.status} {r.latency_ms}ms" for r in rows)
