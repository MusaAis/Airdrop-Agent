
async def run_aging(wallet, chain, db):
    """Send 2-3 tiny self-transfers to age wallet history before actual warmup."""
    import random, asyncio
    from backend.wallet.hd_generator import derive_hd_wallet, get_master_seed
    from backend.wallet.crypto import decrypt_private_key
    from backend.config import MASTER_PASSWORD
    from backend.chains.rpc_pool import get_web3

    w3 = await get_web3(chain)
    if wallet.is_hd:
        wdata = derive_hd_wallet(wallet.hd_index)
        priv_key = wdata['private_key']
    else:
        priv_key = decrypt_private_key(wallet.encrypted_private_key, MASTER_PASSWORD)
    account = w3.eth.account.from_key(priv_key)

    for i in range(random.randint(2, 3)):
        nonce = await w3.eth.get_transaction_count(wallet.address)
        if chain.gas_token_is_native:
            tx = {
                'to': wallet.address,
                'value': w3.to_wei(0.00001, 'ether'),
                'gas': 21000,
                'gasPrice': await w3.eth.gas_price,
                'nonce': nonce,
                'chainId': chain.chain_id,
            }
        else:
            # ERC20 transfer of 0.01 token
            from web3 import Web3
            token_contract = w3.eth.contract(
                address=Web3.to_checksum_address(chain.gas_token_contract),
                abi=[{"constant":False,"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"}]
            )
            amount = 1 * (10 ** chain.gas_token_decimals)
            tx = token_contract.functions.transfer(wallet.address, amount).build_transaction({
                'from': wallet.address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': await w3.eth.gas_price,
            })
        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.rawTransaction)
        await asyncio.sleep(random.randint(10, 60))

import asyncio, logging, random
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Wallet, Chain
from backend.chains.rpc_pool import get_web3
from backend.wallet.hd_generator import derive_hd_wallet, get_master_seed
from backend.wallet.crypto import decrypt_private_key
from backend.config import MASTER_PASSWORD
from datetime import datetime, timezone

logger = logging.getLogger("airdrop.warmup")

async def run_warmup(db: AsyncSession, wallet: Wallet, chain: Chain):
    if wallet.warmup_complete:
        return
    # Get private key
    if wallet.is_hd:
        wallet_data = derive_hd_wallet(wallet.hd_index)
        private_key = wallet_data["private_key"]
    else:
        private_key = decrypt_private_key(wallet.encrypted_private_key, MASTER_PASSWORD)

    w3 = await get_web3(chain)
    account = w3.eth.account.from_key(private_key)
    nonce = await w3.eth.get_transaction_count(wallet.address)

    if chain.gas_token_is_native:
        tx = {
            'to': wallet.address,
            'value': w3.to_wei(0.0001, 'ether'),
            'gas': 21000,
            'gasPrice': await w3.eth.gas_price,
            'nonce': nonce,
            'chainId': chain.chain_id,
        }
        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.rawTransaction)
        logger.info(f"Warmup self-transfer native: {tx_hash.hex()}")
    else:
        # ERC20 transfer of gas token to self
        from web3 import Web3
        token_contract = w3.eth.contract(
            address=Web3.to_checksum_address(chain.gas_token_contract),
            abi=[{"constant":False,"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"}]
        )
        amount = 1 * (10 ** chain.gas_token_decimals)  # 1 token unit
        tx = token_contract.functions.transfer(wallet.address, amount).build_transaction({
            'from': wallet.address,
            'nonce': nonce,
            'gas': 100000,
            'gasPrice': await w3.eth.gas_price,
        })
        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.rawTransaction)
        logger.info(f"Warmup self-transfer ERC20: {tx_hash.hex()}")
    wallet.warmup_started_at = datetime.now(timezone.utc)
    await db.commit()

async def _run_aging_simple(wallet, chain, db):
    """Send 2-3 tiny self-transfers to age wallet history."""
    for i in range(random.randint(2, 3)):
        if chain.gas_token_is_native:
            # send 0.00001 ETH to self
            tx = {
                'to': wallet.address,
                'value': w3.to_wei(0.00001, 'ether'),
                'gas': 21000,
                'gasPrice': await w3.eth.gas_price,
                'nonce': await w3.eth.get_transaction_count(wallet.address),
                'chainId': chain.chain_id,
            }
        else:
            # ERC20 transfer of 0.1 token
            ...
        # sign & send
        # wait random delay (10-60 sec)
        await asyncio.sleep(random.randint(10, 60))

