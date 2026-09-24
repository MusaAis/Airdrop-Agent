import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Transaction
from backend.core.stuck_tx_handler import handle_stuck_tx
from backend.chains.rpc_pool import get_web3
from backend.chains.manager import get_chain
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.tx")

async def handle_tx_stuck(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    txs = (await db.execute(select(Transaction).where(Transaction.status=="pending"))).scalars().all()
    if not txs: return "No pending transactions."
    return "\n".join(f"TX {tx.tx_hash[:10]}... wallet {tx.wallet_id}" for tx in txs)

async def handle_tx_speedup(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: tx.speedup <tx_id>"
    tx = await db.get(Transaction, int(args[0]))
    if not tx: return "Transaction not found."
    if confirmation is None: return "⚠️ Speed up this transaction? Reply 'confirm'"
    chain = await get_chain(db, tx.chain_id)
    w3 = await get_web3(chain)
    # Build a minimal task context to call handle_stuck_tx
    # handle_stuck_tx expects a task object and tx_hash; we can call it directly
    from backend.tasks.base import BaseTask
    # We'll just implement a simple speed-up by resending with higher gas
    try:
        old_tx = await w3.eth.get_transaction(tx.tx_hash)
        new_tx = dict(old_tx)
        new_tx['gasPrice'] = int(old_tx['gasPrice'] * 1.2)
        # Need to sign with wallet's private key – we can derive from DB if HD
        from backend.wallet.hd_generator import derive_hd_wallet, get_master_seed
        from backend.wallet.crypto import decrypt_private_key
        from backend.wallet.manager import get_wallet
        from backend.config import MASTER_PASSWORD
        wallet = await get_wallet(db, tx.wallet_id)
        if wallet.is_hd:
            wdata = derive_hd_wallet(wallet.hd_index)
            priv_key = wdata["private_key"]
        else:
            priv_key = decrypt_private_key(wallet.encrypted_private_key, MASTER_PASSWORD)
        account = w3.eth.account.from_key(priv_key)
        signed = account.sign_transaction(new_tx)
        new_hash = await w3.eth.send_raw_transaction(signed.rawTransaction)
        tx.tx_hash = new_hash.hex()
        tx.gas_price = new_tx['gasPrice']
        await db.commit()
        return f"Speed up sent. New hash: {new_hash.hex()}"
    except Exception as e:
        return f"Error: {e}"

async def handle_tx_cancel(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: tx.cancel <tx_id>"
    tx = await db.get(Transaction, int(args[0]))
    if not tx: return "Transaction not found."
    if confirmation is None: return "⚠️ Cancel this transaction? Reply 'confirm'"
    chain = await get_chain(db, tx.chain_id)
    w3 = await get_web3(chain)
    try:
        # Cancel by sending a zero-value tx with same nonce and higher gas
        old_tx = await w3.eth.get_transaction(tx.tx_hash)
        cancel_tx = {
            'to': old_tx['from'],
            'value': 0,
            'gas': 21000,
            'gasPrice': int(old_tx['gasPrice'] * 1.2),
            'nonce': old_tx['nonce'],
            'chainId': chain.chain_id,
        }
        from backend.wallet.hd_generator import derive_hd_wallet, get_master_seed
        from backend.wallet.crypto import decrypt_private_key
        from backend.wallet.manager import get_wallet
        from backend.config import MASTER_PASSWORD
        wallet = await get_wallet(db, tx.wallet_id)
        if wallet.is_hd:
            wdata = derive_hd_wallet(wallet.hd_index)
            priv_key = wdata["private_key"]
        else:
            priv_key = decrypt_private_key(wallet.encrypted_private_key, MASTER_PASSWORD)
        account = w3.eth.account.from_key(priv_key)
        signed = account.sign_transaction(cancel_tx)
        new_hash = await w3.eth.send_raw_transaction(signed.rawTransaction)
        tx.status = "cancelled"
        await db.commit()
        return f"Cancellation sent. Hash: {new_hash.hex()}"
    except Exception as e:
        return f"Error: {e}"

async def handle_tx_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: tx.status <hash>"
    tx_hash = args[0]
    tx = (await db.execute(select(Transaction).where(Transaction.tx_hash==tx_hash))).scalar_one_or_none()
    if not tx: return "Transaction not found."
    return f"Status: {tx.status}, Block: {tx.block_number}, Gas: {tx.gas_cost_usd}"

async def handle_tx_failed(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    txs = (await db.execute(select(Transaction).where(Transaction.status=="failed"))).scalars().all()
    return "\n".join(f"{tx.tx_hash[:10]}... wallet {tx.wallet_id}: {tx.error_message}" for tx in txs)

async def handle_tx_verify(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: tx.verify <wallet_id>"
    wallet_id = int(args[0])
    txs = (await db.execute(select(Transaction).where(Transaction.wallet_id==wallet_id))).scalars().all()
    if not txs: return "No transactions for this wallet."
    results = []
    for tx in txs:
        try:
            chain = await get_chain(db, tx.chain_id)
            w3 = await get_web3(chain)
            receipt = await w3.eth.get_transaction_receipt(tx.tx_hash)
            onchain_status = "confirmed" if receipt and receipt.status==1 else "failed/missing"
            results.append(f"{tx.tx_hash[:10]}... DB:{tx.status} chain:{onchain_status}")
        except:
            results.append(f"{tx.tx_hash[:10]}... error checking")
    return "\n".join(results)
