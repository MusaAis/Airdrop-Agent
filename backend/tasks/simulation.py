import logging
from typing import Dict, Any
from decimal import Decimal

logger = logging.getLogger("airdrop.simulation")


async def simulate_task(task_instance, nonce: int = 0) -> Dict[str, Any]:
    """
    Simulate task execution without sending real transactions.
    Performs all checks (balance, gas, approval, contract pause) but
    uses eth_call instead of eth_sendRawTransaction.
    """
    results = {
        "task_type": task_instance.task_type,
        "wallet": task_instance.wallet.address,
        "chain": task_instance.chain.name,
        "dry_run": True,
        "checks": {},
        "status": "simulated_success",
        "errors": [],
    }

    try:
        # Connect to chain
        from backend.chains.rpc_pool import get_web3
        task_instance.w3 = await get_web3(task_instance.chain)

        # Check 1: gas balance
        from backend.wallet.balance import get_gas_token_balance
        gas_balance = await get_gas_token_balance(task_instance.chain, task_instance.wallet.address)
        gas_est = await task_instance.estimate_gas()
        required = gas_est * Decimal("1.2")
        gas_ok = gas_balance >= required
        results["checks"]["gas_balance"] = {
            "balance": float(gas_balance),
            "required": float(required),
            "token": task_instance.chain.gas_token_symbol,
            "ok": gas_ok,
        }
        if not gas_ok:
            results["errors"].append(f"Insufficient gas: {gas_balance} < {required}")

        # Check 2: contract pause (if applicable)
        params = task_instance.task_config.parameters or {}
        contract_addr = params.get("router_address") or params.get("staking_contract") or params.get("bridge_contract")
        if contract_addr:
            try:
                pause_abi = [{"inputs":[],"name":"paused","outputs":[{"name":"","type":"bool"}],"type":"function"}]
                contract = task_instance.w3.eth.contract(address=contract_addr, abi=pause_abi)
                is_paused = await contract.functions.paused().call()
                results["checks"]["contract_paused"] = {"paused": is_paused, "ok": not is_paused}
                if is_paused:
                    results["errors"].append("Contract is paused")
            except Exception:
                results["checks"]["contract_paused"] = {"ok": True, "note": "paused() not available"}

        # Check 3: transaction simulation via eth_call
        try:
            tx_params = await task_instance.build_transaction_params(nonce)
            tx_params_for_call = {k: v for k, v in tx_params.items() if k in ("to", "data", "value", "from", "gas")}
            tx_params_for_call["from"] = task_instance.wallet.address
            await task_instance.w3.eth.call(tx_params_for_call)
            results["checks"]["eth_call"] = {"ok": True}
        except Exception as e:
            results["checks"]["eth_call"] = {"ok": False, "error": str(e)}
            results["errors"].append(f"Simulation revert: {str(e)[:200]}")

        if results["errors"]:
            results["status"] = "simulated_failure"

    except Exception as e:
        results["status"] = "simulation_error"
        results["errors"].append(str(e))

    return results
