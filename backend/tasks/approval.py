import asyncio
import random
import logging
from typing import Dict
from web3 import AsyncWeb3
from decimal import Decimal
from backend.core.nonce_manager import lock_nonce, release_nonce
from backend.wallet.balance import get_gas_token_balance

logger = logging.getLogger("airdrop.approval")

async def handle_token_approval(task) -> Dict:
    token_contract_addr = task.token_in_address
    spender = task.spender_address
    amount = task.amount_to_spend

    # Standard ERC20 ABI
    abi = [
        {"constant":False,"inputs":[{"name":"spender","type":"address"},{"name":"value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},
        {"constant":True,"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"}
    ]
    contract = task.w3.eth.contract(address=token_contract_addr, abi=abi)

    # Check current allowance
    current_allowance = await contract.functions.allowance(task.wallet.address, spender).call()
    if current_allowance >= amount:
        logger.info(f"Allowance sufficient: {current_allowance} >= {amount}")
        return {"success": True, "approval_tx": None}

    # Approve exact amount
    try:
        nonce = await lock_nonce(task.db, task.wallet.id, task.chain.id)
        tx = contract.functions.approve(spender, amount).build_transaction({
            'from': task.wallet.address,
            'nonce': nonce,
            'gas': 100000,
            'gasPrice': await task.w3.eth.gas_price,
        })
        signed = await task.sign_transaction(tx)
        tx_hash = await task.w3.eth.send_raw_transaction(signed.rawTransaction)
        await release_nonce(task.db, task.wallet.id, task.chain.id, increment=True)
        logger.info(f"Approval TX sent: {tx_hash.hex()}")

        # Wait for receipt (USDT may not return a bool, so we check receipt status)
        receipt = await task.monitor_tx(tx_hash, timeout=180)
        if not receipt or receipt.status != 1:
            return {"success": False, "reason": "approval_failed"}

        # Re-check allowance after approval
        new_allowance = await contract.functions.allowance(task.wallet.address, spender).call()
        if new_allowance < amount:
            return {"success": False, "reason": "allowance still insufficient after approval"}

        # Human-like delay
        delay = random.randint(30, 90)
        logger.info(f"Waiting {delay}s after approval")
        await asyncio.sleep(delay)

        # Re-check gas balance
        gas_balance = await get_gas_token_balance(task.chain, task.wallet.address)
        required_gas = await task.estimate_gas() * Decimal("1.2")
        if gas_balance < required_gas:
            return {"success": False, "reason": "low_gas_after_approval"}

        return {"success": True, "approval_tx": tx_hash.hex()}
    except Exception as e:
        await release_nonce(task.db, task.wallet.id, task.chain.id, increment=False)
        return {"success": False, "reason": str(e)}
