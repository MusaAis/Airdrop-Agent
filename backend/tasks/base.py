import asyncio
import random
import time
import logging
from decimal import Decimal
from typing import Optional, Dict, Any
from web3 import AsyncWeb3
from backend.models import Chain, Wallet, TaskConfig, Project, Transaction, TokenApproval
from backend.database import async_session
from backend.chains.rpc_pool import get_web3
from backend.wallet.balance import get_gas_token_balance, fee_to_gas_token, chain_coingecko_id
from backend.core.nonce_manager import lock_nonce, release_nonce
from backend.chains.price_oracle import get_usd_price
from backend.chains.gas import get_current_gas_price, is_gas_spike
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("airdrop.tasks")

class BaseTask:
    task_type: str = "generic"

    def __init__(self, task_config: TaskConfig, wallet: Wallet, chain: Chain, project: Project, db_session):
        self.task_config = task_config
        self.wallet = wallet
        self.chain = chain
        self.project = project
        self.db = db_session
        self.w3: AsyncWeb3 = None
        self.gas_token_symbol = chain.gas_token_symbol
        self.gas_is_native = chain.gas_token_is_native
        self.token_decimals = 18  # default for native; override for tokens

    # ------------------------------------------------------------------
    # Amount randomisation — uses per-task config (min/max/distribution)
    # and falls back to wallet settings when per-task overrides are set.
    #
    # Cached per task instance (self._cached_amount) because execute() may
    # call build_transaction_params() twice — once before approval, once
    # again with a fresh nonce after approval succeeds. If the second call
    # re-rolled a new random amount, it could exceed the amount actually
    # approved on-chain in the first pass, causing the main tx to revert
    # for insufficient allowance. Caching guarantees both calls agree.
    # ------------------------------------------------------------------
    def randomize_amount(self) -> Decimal:
        """Return a randomised transaction amount respecting task config.
        Stable across multiple calls within the same execute() run — see note above."""
        if getattr(self, "_cached_amount", None) is not None:
            return self._cached_amount

        from backend.wallet.behavior_randomizer import weighted_random_amount

        tc = self.task_config
        min_amt = float(tc.min_amount or 0.001)
        max_amt = float(tc.max_amount or min_amt * 2)
        distribution = tc.amount_distribution or "weighted_low"

        # Bidirectional support: if task_config says bidirectional and this
        # call is for the reverse leg the subclass sets self._use_reverse=True
        if getattr(self, "_use_reverse", False) and tc.bidirectional:
            pass  # amounts are the same either way; direction is handled in build_transaction_params

        amount = weighted_random_amount(min_amt, max_amt, distribution)
        self._cached_amount = Decimal(str(amount))
        return self._cached_amount

    # ------------------------------------------------------------------
    # Main execute() — fixed approval ordering (build params first so
    # subclasses can set self.needs_approval, then check it)
    # ------------------------------------------------------------------
    async def execute(self) -> Dict[str, Any]:
        """Complete execution flow. Returns tx result dict."""
        # 5. Connect to chain
        self.w3 = await get_web3(self.chain)
        # Gas spike guard
        from backend.core.gas_spike_guard import check_gas_spike
        if await check_gas_spike(self.chain):
            logger.warning(f"Gas spike detected on {self.chain.name}, deferring task")
            return {"status": "skipped", "reason": "gas_spike"}
        # 6. Estimate gas cost
        gas_estimation = await self.estimate_gas()
        # 8. Check gas token balance >= estimate + 20% buffer
        gas_balance = await get_gas_token_balance(self.chain, self.wallet.address)
        # gas_estimation is in the chain's smallest unit (wei); gas_balance is in human
        # units (ether). Convert before comparing, otherwise every task skips as low_gas.
        required_gas = fee_to_gas_token(self.chain, gas_estimation) * Decimal("1.2")
        if gas_balance < required_gas:
            logger.warning(f"Low gas for {self.wallet.address}: {gas_balance} < {required_gas}")
            return {"status": "skipped", "reason": "low_gas"}

        # 12. Check contract paused
        if hasattr(self, 'check_paused') and await self.check_paused():
            return {"status": "skipped", "reason": "contract_paused"}

        # 14. Lock nonce FIRST — simulation then uses the real nonce so
        #     contracts that check sender state (nonce-dependent) don't
        #     produce spurious reverts.
        nonce = await lock_nonce(self.db, self.wallet.id, self.chain.id)
        try:
            # 15. Build transaction params — subclasses set self.needs_approval
            #     and self.token_decimals as a side effect of this call
            tx_params = await self.build_transaction_params(nonce)

            # 10. Approval flow — checked AFTER build_transaction_params so
            #     subclasses have had a chance to set self.needs_approval.
            #
            #     IMPORTANT: the approval tx is a SEPARATE on-chain transaction
            #     from the main tx, and needs its OWN nonce. handle_approval()
            #     calls lock_nonce() internally — but we are still holding the
            #     lock we took above, so that call would poll for up to 30s
            #     waiting on a lock only we hold, then time out and fail every
            #     single approval-gated task. Fix: release our lock before
            #     calling handle_approval(), let it acquire+use+release its own
            #     nonce for the approval tx, then re-lock to get a *fresh* nonce
            #     for the main tx (which will correctly be approval_nonce + 1).
            #
            #     Dry-run: the approval is a REAL broadcast (spends gas, sets an
            #     on-chain allowance), so it must never happen in dry-run. We skip
            #     it, keep the nonce we already hold, and skip the eth_call below
            #     (it would revert for lack of allowance and fail the dry run).
            from backend.core.kill_switch import is_dry_run as _is_dry_run
            approval_deferred = False
            if getattr(self, 'needs_approval', False):
                if _is_dry_run():
                    approval_deferred = True
                    logger.info(
                        f"[DRY RUN] {self.task_type} for wallet={self.wallet.address} needs a "
                        f"token approval - not broadcasting it"
                    )
                else:
                    await release_nonce(self.db, self.wallet.id, self.chain.id, increment=False)
                    approval_result = await self.handle_approval()
                    if not approval_result["success"]:
                        return approval_result
                    # Re-lock to get a fresh nonce for the main tx, and rebuild the
                    # tx params with it (the old `nonce`/tx_params are now stale —
                    # the approval tx consumed the nonce they were built with).
                    nonce = await lock_nonce(self.db, self.wallet.id, self.chain.id)
                    tx_params = await self.build_transaction_params(nonce)

            # 11. Simulate tx (dry run) with the real nonce — pre-flight check
            if approval_deferred:
                sim_result = {"success": True, "skipped": "approval not sent (dry run)"}
            else:
                sim_result = await self.simulate_transaction_with_params(tx_params)
            if not sim_result["success"]:
                await release_nonce(self.db, self.wallet.id, self.chain.id, increment=False)
                return {"status": "failed", "reason": "simulation_failed", "details": sim_result}

            # Apply per-wallet gas multiplier variance so every wallet has a
            # slightly different gas price (anti-detection, uses behavior_randomizer)
            try:
                from backend.wallet.behavior_randomizer import apply_gas_multiplier
                from backend.wallet.manager import get_wallet_settings
                ws = await get_wallet_settings(self.db, self.wallet.id)
                if "gasPrice" in tx_params and tx_params["gasPrice"]:
                    tx_params["gasPrice"] = apply_gas_multiplier(tx_params["gasPrice"], ws)
            except Exception:
                pass  # non-fatal — proceed with original gas price

            # 16. Submit transaction
            #
            # Dry-run gate: previously is_dry_run()/DRY_RUN was only checked in
            # agent.py's periodic_fill() loop, which controls whether NEW items
            # get added to the queue. It was never checked here, at the actual
            # broadcast point — so anything already queued when dry-run was
            # toggled on would still submit a real, fund-spending transaction,
            # directly contradicting the Telegram bot's own message ("agent
            # will simulate but not submit transactions"). Checking it here,
            # right before send_raw_transaction, is the one chokepoint every
            # task type (swap/bridge/stake/liquidity/transfer) passes through.
            from backend.core.kill_switch import is_dry_run
            if is_dry_run():
                await release_nonce(self.db, self.wallet.id, self.chain.id, increment=False)
                logger.info(
                    f"[DRY RUN] Would submit {self.task_type} tx for wallet="
                    f"{self.wallet.address} chain={self.chain.id} — not broadcasting"
                )
                from backend.models import Log
                self.db.add(Log(
                    wallet_id=self.wallet.id,
                    chain_id=self.chain.id,
                    task_config_id=self.task_config.id,
                    project_id=self.project.id,
                    task_name=self.task_type,
                    status="simulated",
                    is_dry_run=True,
                    created_at=datetime.now(timezone.utc),
                ))
                await self.db.commit()
                return {"status": "simulated", "reason": "dry_run", "would_submit": tx_params}

            signed_tx = await self.sign_transaction(tx_params)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            # Record transaction in DB (status pending)
            tx_record = Transaction(
                wallet_id=self.wallet.id,
                task_config_id=self.task_config.id,
                chain_id=self.chain.id,
                tx_hash=tx_hash.hex(),
                status="pending",
                gas_price=tx_params.get("gasPrice", 0),
                created_at=datetime.now(timezone.utc)
            )
            self.db.add(tx_record)
            await self.db.commit()
            # 17. Release nonce lock after submission
            await release_nonce(self.db, self.wallet.id, self.chain.id, increment=True)

            # 18. Monitor confirmation
            receipt = await self.monitor_tx(tx_hash)
            if receipt and receipt.status == 1:
                tx_record.status = "confirmed"
                tx_record.confirmed_at = datetime.now(timezone.utc)
                tx_record.block_number = receipt.blockNumber
                await self._record_fee(tx_record, receipt)
                await self.db.commit()
                logger.info(f"TX confirmed: {tx_hash.hex()}")
                return {"status": "success", "tx_hash": tx_hash.hex(), "receipt": dict(receipt),
                        "gas_cost_usd": tx_record.gas_cost_usd}
            else:
                tx_record.status = "failed"
                if receipt:
                    tx_record.block_number = receipt.blockNumber
                    await self._record_fee(tx_record, receipt)
                    tx_record.error_message = "transaction reverted on-chain"
                else:
                    tx_record.error_message = "no receipt before timeout (stuck or replaced)"
                await self.db.commit()
                return {"status": "failed", "reason": "tx_failed_onchain"}
        except Exception as e:
            await release_nonce(self.db, self.wallet.id, self.chain.id, increment=False)
            logger.error(f"TX submission error: {e}")
            rec = locals().get("tx_record")
            if rec is not None:
                try:
                    rec.status = "failed"
                    rec.error_message = str(e)[:500]
                    await self.db.commit()
                except Exception:
                    await self.db.rollback()
            return {"status": "failed", "reason": str(e)}

    async def _record_fee(self, tx_record, receipt) -> None:
        """Fill gas_used / gas_token / gas_cost_native / gas_cost_usd from a receipt. Reverted
        transactions still burn gas, so this runs for failures too. Never raises: a price
        lookup failure only leaves the USD estimate empty."""
        try:
            gas_used = int(receipt.gasUsed)
            price = receipt.get("effectiveGasPrice") or tx_record.gas_price or 0
            native = fee_to_gas_token(self.chain, Decimal(gas_used) * Decimal(price))
            tx_record.gas_used = gas_used
            tx_record.gas_token = self.chain.gas_token_symbol
            tx_record.gas_cost_native = float(native)
            try:
                usd_price = await asyncio.wait_for(get_usd_price(chain_coingecko_id(self.chain)), 8)
                if usd_price is not None:
                    tx_record.gas_cost_usd = float(native) * usd_price
            except Exception:
                pass  # USD is only an estimate (and meaningless on testnets)
        except Exception as e:
            logger.warning(f"Could not record fee for {tx_record.tx_hash}: {e}")

    async def estimate_gas(self) -> Decimal:
        """Default gas estimation (can be overridden by subclasses)."""
        return Decimal("21000") * Decimal(await self.w3.eth.gas_price)

    async def simulate_transaction(self) -> Dict[str, Any]:
        """Dry run via eth_call."""
        try:
            tx = await self.build_transaction_params(0)  # nonce=0 for simulation
            await self.w3.eth.call(tx)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def simulate_transaction_with_params(self, tx_params: Dict) -> Dict[str, Any]:
        """Dry run using already-built tx_params (real nonce) — avoids double
        build_transaction_params call and uses the actual nonce for accuracy."""
        try:
            await self.w3.eth.call(tx_params)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def handle_approval(self) -> Dict[str, Any]:
        """Exact-amount token approval with JIT delay."""
        from backend.tasks.approval import handle_token_approval
        result = await handle_token_approval(self)
        return result

    async def build_transaction_params(self, nonce: int) -> Dict:
        """To be implemented by each task type."""
        raise NotImplementedError

    async def sign_transaction(self, tx_params: Dict):
        """Sign with wallet's private key (derived at runtime)."""
        from backend.wallet.hd_generator import derive_hd_wallet, get_master_seed
        from backend.wallet.crypto import decrypt_private_key
        from backend.config import MASTER_PASSWORD
        if self.wallet.is_hd:
            wallet_data = derive_hd_wallet(self.wallet.hd_index)
            priv_key = wallet_data["private_key"]
        else:
            priv_key = decrypt_private_key(self.wallet.encrypted_private_key, MASTER_PASSWORD)
        account = self.w3.eth.account.from_key(priv_key)
        return account.sign_transaction(tx_params)

    async def monitor_tx(self, tx_hash, timeout: int = 300):
        """Poll for confirmation with exponential backoff."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                receipt = await self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return receipt
            except:
                pass
            await asyncio.sleep(random.uniform(2, 5))
        # stuck
        from backend.core.stuck_tx_handler import handle_stuck_tx
        await handle_stuck_tx(self, tx_hash)
        return None
