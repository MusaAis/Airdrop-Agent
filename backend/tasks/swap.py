import asyncio
import random
from decimal import Decimal
from typing import Dict
from backend.tasks.base import BaseTask
import logging

logger = logging.getLogger("airdrop.swap")

class SwapTask(BaseTask):
    task_type = "swap"

    async def build_transaction_params(self, nonce: int) -> Dict:
        """Construct a UniswapV2-style swap transaction."""
        tc = self.task_config
        router_address = tc.parameters.get("router_address")
        if not router_address:
            raise ValueError("Missing router_address in task config parameters")

        # Bidirectional: flip token_in/token_out on random runs
        from backend.wallet.behavior_randomizer import should_flip_direction
        flip = should_flip_direction(tc.bidirectional)
        if flip and tc.token_in_reverse and tc.token_out_reverse:
            token_in = tc.token_in_reverse
            token_out = tc.token_out_reverse
        else:
            token_in = tc.token_in
            token_out = tc.token_out

        if not token_in or not token_out:
            raise ValueError("Missing token_in or token_out in task config")

        amount_in = self.randomize_amount()
        amount_in_wei = int(amount_in * (10 ** self.token_decimals))
        deadline = int(asyncio.get_event_loop().time()) + 60 * tc.deadline_mins

        # Slippage: use task_config's slippage_tolerance (default 0.5 %)
        slippage = float(tc.slippage_tolerance or 0.005)

        w3 = self.w3
        gas_price = await w3.eth.gas_price

        # Determine if input is native token
        if token_in.upper() == self.chain.gas_token_symbol and self.chain.gas_token_is_native:
            # ETH → Token: swapExactETHForTokens
            # amountOutMin estimated via getAmountsOut if available, else use slippage factor
            amount_out_min = await self._get_amount_out_min(
                router_address, amount_in_wei,
                [await self._get_wrapped_native(), w3.to_checksum_address(token_out)],
                slippage
            )
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
            contract = w3.eth.contract(address=w3.to_checksum_address(router_address), abi=abi)
            path = [await self._get_wrapped_native(), w3.to_checksum_address(token_out)]
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
            # Token → Token / Token → ETH: swapExactTokensForTokens
            # Resolve address if caller passed a symbol
            token_in_addr = await self._resolve_token_address(token_in)
            token_out_addr = await self._resolve_token_address(token_out)

            path = [w3.to_checksum_address(token_in_addr), w3.to_checksum_address(token_out_addr)]
            amount_out_min = await self._get_amount_out_min(router_address, amount_in_wei, path, slippage)

            # Signal that we need an ERC-20 approval before sending
            self.needs_approval = True
            self.token_in_address = token_in_addr
            self.spender_address = router_address
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
            contract = w3.eth.contract(address=w3.to_checksum_address(router_address), abi=abi)
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
                "chainId": self.chain.chain_id,  # was missing in ERC20 branch
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
