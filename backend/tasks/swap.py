import asyncio
import random
import time
from decimal import Decimal
from typing import Dict
from backend.tasks.base import BaseTask
import logging

logger = logging.getLogger("airdrop.swap")

_ERC20_DECIMALS_ABI = [{
    "inputs": [], "name": "decimals",
    "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
    "stateMutability": "view", "type": "function",
}]


class SwapTask(BaseTask):
    task_type = "swap"

    def _is_native(self, token: str) -> bool:
        return token.upper() == self.chain.gas_token_symbol.upper() and self.chain.gas_token_is_native

    async def _get_decimals(self, token: str) -> int:
        """Real decimals for the INPUT token. Previously self.token_decimals
        (hardcoded 18) was used for every token, so a 6-decimal token like
        USDC produced an amount 10^12 too large. Never guesses: if the value
        can't be determined, raises (classified as config_error)."""
        if self._is_native(token):
            return 18
        from sqlalchemy import select, func
        from backend.models import ChainToken
        if token.startswith("0x") and len(token) == 42:
            row = (await self.db.execute(
                select(ChainToken).where(
                    ChainToken.chain_id == self.chain.id,
                    func.lower(ChainToken.contract_address) == token.lower(),
                )
            )).scalar_one_or_none()
            if row:
                return int(row.decimals)
            try:
                contract = self.w3.eth.contract(
                    address=self.w3.to_checksum_address(token), abi=_ERC20_DECIMALS_ABI
                )
                return int(await contract.functions.decimals().call())
            except Exception as e:
                raise ValueError(f"Cannot resolve decimals for token {token} on chain '{self.chain.name}': {e}")
        from backend.chains.token_registry import resolve_token
        _, decimals = await resolve_token(self.db, self.chain.id, token)
        return int(decimals)

    async def build_transaction_params(self, nonce: int) -> Dict:
        """Construct a UniswapV2-style swap transaction."""
        tc = self.task_config
        router_address = tc.parameters.get("router_address")
        if not router_address:
            raise ValueError("Missing router_address in task config parameters")

        # Bidirectional: flip token_in/token_out on random runs. The choice is
        # made ONCE per task run and cached — execute() builds params twice
        # when an approval is needed, and a re-roll could approve token A then
        # swap token B.
        from backend.wallet.behavior_randomizer import should_flip_direction
        if getattr(self, "_cached_flip", None) is None:
            self._cached_flip = should_flip_direction(tc.bidirectional)
        flip = self._cached_flip
        if flip and tc.token_in_reverse and tc.token_out_reverse:
            token_in = tc.token_in_reverse
            token_out = tc.token_out_reverse
        else:
            token_in = tc.token_in
            token_out = tc.token_out

        if not token_in or not token_out:
            raise ValueError("Missing token_in or token_out in task config")

        w3 = self.w3
        router = w3.to_checksum_address(router_address)

        self.token_decimals = await self._get_decimals(token_in)
        amount_in = self.randomize_amount()
        amount_in_wei = int(amount_in * (10 ** self.token_decimals))
        # Fix: was asyncio loop.time() (a monotonic clock, not unix time), which
        # put the deadline in 1970 and made routers revert with EXPIRED.
        deadline = int(time.time()) + 60 * tc.deadline_mins

        # Slippage: use task_config's slippage_tolerance (default 0.5 %)
        slippage = float(tc.slippage_tolerance or 0.005)

        gas_price = await w3.eth.gas_price

        # Determine if input is native token
        if self._is_native(token_in):
            # ETH → Token: swapExactETHForTokens
            wrapped = await self._get_wrapped_native()
            path = [wrapped, w3.to_checksum_address(await self._resolve_token_address(token_out))]
            amount_out_min = await self._get_amount_out_min(router, amount_in_wei, path, slippage)
            abi = [{
                "inputs": [
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactETHForTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "payable",
                "type": "function"
            }]
            contract = w3.eth.contract(address=router, abi=abi)
            tx = contract.functions.swapExactETHForTokens(
                amount_out_min,
                path,
                self.wallet.address,
                deadline
            ).build_transaction({
                "from": self.wallet.address,
                "value": amount_in_wei,
                "gas": 250000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
            })
        else:
            # Token → Token: swapExactTokensForTokens
            token_in_addr = w3.to_checksum_address(await self._resolve_token_address(token_in))
            token_out_addr = w3.to_checksum_address(await self._resolve_token_address(token_out))

            path = [token_in_addr, token_out_addr]
            amount_out_min = await self._get_amount_out_min(router, amount_in_wei, path, slippage)

            # Signal that we need an ERC-20 approval before sending
            # (checksummed: the approval flow builds a contract with these)
            self.needs_approval = True
            self.token_in_address = token_in_addr
            self.spender_address = router
            self.amount_to_spend = amount_in_wei

            abi = [{
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "nonpayable",
                "type": "function"
            }]
            contract = w3.eth.contract(address=router, abi=abi)
            tx = contract.functions.swapExactTokensForTokens(
                amount_in_wei,
                amount_out_min,
                path,
                self.wallet.address,
                deadline
            ).build_transaction({
                "from": self.wallet.address,
                "gas": 250000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
            })
        return tx

    async def _get_wrapped_native(self) -> str:
        """Return WETH / WBNB etc. address from chain's token registry."""
        from backend.chains.token_registry import get_wrapped_native
        try:
            addr = await get_wrapped_native(self.chain.id, self.db)
            if addr:
                return self.w3.to_checksum_address(addr)
        except Exception:
            pass
        # Fallback: read from task_config parameters
        wrapped = self.task_config.parameters.get("wrapped_native_address")
        if wrapped:
            return self.w3.to_checksum_address(wrapped)
        raise ValueError(
            f"Cannot resolve wrapped native token for chain {self.chain.name}. "
            "Add 'wrapped_native_address' to task_config.parameters."
        )

    async def _resolve_token_address(self, token: str) -> str:
        """Resolve a symbol (e.g. 'USDC') to its contract address, or pass
        through if already an address."""
        if token.startswith("0x") and len(token) == 42:
            return token
        from backend.chains.token_registry import get_token_address
        try:
            addr = await get_token_address(self.chain.id, token, self.db)
            if addr:
                return addr
        except Exception:
            pass
        raise ValueError(
            f"Cannot resolve token '{token}' to an address on chain "
            f"'{self.chain.name}'. Add it to the chain's token registry."
        )

    async def _get_amount_out_min(self, router: str, amount_in: int, path: list, slippage: float) -> int:
        """Call getAmountsOut on the router to get expected output, then apply slippage.
        Falls back to 0 if the call fails (keeps old behaviour, logs a warning)."""
        try:
            abi = [{
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "name": "getAmountsOut",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            }]
            contract = self.w3.eth.contract(address=self.w3.to_checksum_address(router), abi=abi)
            amounts = await contract.functions.getAmountsOut(amount_in, path).call()
            expected_out = amounts[-1]
            return int(expected_out * (1 - slippage))
        except Exception as e:
            logger.warning(f"getAmountsOut failed ({e}), using amountOutMin=0")
            return 0

    async def estimate_gas(self) -> Decimal:
        gas_price = await self.w3.eth.gas_price
        return Decimal(250000) * Decimal(gas_price)
