import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Chain
from backend.chains.manager import list_chains, get_chain, create_chain, update_chain, add_token, list_tokens
from backend.chains.rpc_checker import check_all_rpcs
from backend.chains.gas import get_current_gas_price
from backend.chains.rpc_pool import get_web3
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.chain")

async def handle_chain_list(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    chains = await list_chains(db)
    if not chains: return "No chains."
    return "\n".join(f"{c.id}: {c.name} (ID:{c.chain_id}) [{c.gas_token_symbol}] enabled:{c.enabled}" for c in chains)

async def handle_chain_add(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<3: return "Usage: chain.add <name> <chain_id> <rpc>"
    name, cid, rpc = args[0], int(args[1]), args[2]
    chain = await create_chain(db, name=name, chain_id=cid, rpc_urls=[rpc], gas_token_symbol="ETH", gas_token_is_native=True, gas_token_decimals=18)
    return f"✅ Chain {chain.name} added (ID:{chain.id})"

async def handle_chain_enable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: chain.enable <id>"
    await update_chain(db, int(args[0]), enabled=True)
    return "✅ Enabled."

async def handle_chain_disable(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: chain.disable <id>"
    if confirmation is None: return "⚠️ Confirm disable chain? Reply 'confirm'"
    await update_chain(db, int(args[0]), enabled=False)
    return "⚠️ Disabled."

async def handle_chain_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: chain.status <id>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    rpc_status = await check_all_rpcs(chain)
    w3 = await get_web3(chain)
    gas = await get_current_gas_price(w3)
    return f"{chain.name}\nRPC: {rpc_status}\nGas: {gas} wei"

async def handle_chain_gas(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: chain.gas <id>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    w3 = await get_web3(chain)
    gas = await get_current_gas_price(w3)
    return f"Gas on {chain.name}: {gas} wei"

async def handle_chain_tokens(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: chain.tokens <id>"
    tokens = await list_tokens(db, int(args[0]))
    if not tokens: return "No tokens."
    return "\n".join(f"{t.symbol}: {t.contract_address} dec:{t.decimals}" for t in tokens)

async def handle_chain_rpc(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: chain.rpc <id> <new_rpc>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    urls = chain.rpc_urls
    urls[0] = args[1]
    chain.rpc_urls = urls
    await db.commit()
    return "Primary RPC updated."

async def handle_chain_add_fallback(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: chain.add_fallback <id> <url>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    urls = chain.rpc_urls
    urls.append(args[1])
    chain.rpc_urls = urls
    await db.commit()
    return "Fallback added."

async def handle_chain_remove_fallback(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: chain.remove_fallback <id> <url>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    urls = chain.rpc_urls
    if args[1] in urls:
        urls.remove(args[1])
        chain.rpc_urls = urls
        await db.commit()
    return "Fallback removed."

async def handle_chain_test_rpc(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: chain.test_rpc <id>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    results = await check_all_rpcs(chain)
    return "\n".join(f"{r['url']}: {r['status']} {r.get('latency_ms','')}ms" for r in results)

async def handle_chain_add_token(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<4: return "Usage: chain.add_token <chain_id> <symbol> <address> <decimals>"
    await add_token(db, chain_id=int(args[0]), symbol=args[1], contract_address=args[2], decimals=int(args[3]))
    return "Token added."

async def handle_chain_gas_token(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: chain.gas_token <id>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    return f"Gas token: {chain.gas_token_symbol} (native: {chain.gas_token_is_native})"

async def handle_chain_set_rate_limit(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: chain.set_rate_limit <id> <req_sec>"
    chain = await get_chain(db, int(args[0]))
    if not chain: return "Chain not found."
    chain.rpc_rate_limit_per_sec = int(args[1])
    await db.commit()
    return "Rate limit set."
