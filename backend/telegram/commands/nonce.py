import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.nonce_manager import get_nonce, sync_nonce_from_chain, release_nonce
from backend.wallet.manager import get_wallet
from backend.chains.manager import get_chain
from backend.telegram.whitelist import is_whitelisted

async def handle_nonce_check(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: nonce.check <wallet_id> <chain_id>"
    wallet = await get_wallet(db, int(args[0]))
    if not wallet: return "Wallet not found."
    nonce = await get_nonce(db, wallet.id, int(args[1]))
    return f"Nonce: {nonce.nonce} (locked: {nonce.locked})"

async def handle_nonce_sync(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: nonce.sync <wallet_id> <chain_id>"
    wallet = await get_wallet(db, int(args[0]))
    if not wallet: return "Wallet not found."
    from backend.chains.rpc_pool import get_web3
    chain = await get_chain(db, int(args[1]))
    w3 = await get_web3(chain)
    onchain_nonce = await w3.eth.get_transaction_count(wallet.address)
    await sync_nonce_from_chain(db, wallet.id, chain.id, onchain_nonce)
    return f"Nonce synced to {onchain_nonce}."

async def handle_nonce_release(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: nonce.release <wallet_id> <chain_id>"
    wallet = await get_wallet(db, int(args[0]))
    if not wallet: return "Wallet not found."
    if confirmation is None: return "⚠️ Confirm release nonce lock? Reply 'confirm'"
    await release_nonce(db, wallet.id, int(args[1]), increment=False)
    return "Nonce lock released."

async def handle_nonce_release_all(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if confirmation is None: return "⚠️ Release ALL nonce locks? Reply 'confirm'"
    from backend.models import WalletNonce
    from sqlalchemy import update
    await db.execute(update(WalletNonce).values(locked=False))
    await db.commit()
    return "All nonce locks released."
