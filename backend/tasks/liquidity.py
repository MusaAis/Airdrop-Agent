import logging
import time
from decimal import Decimal
from typing import Dict, Optional, Tuple
from web3 import Web3
from backend.tasks.base import BaseTask

logger = logging.getLogger("airdrop.tasks.liquidity")


class ProvideLiquidityTask(BaseTask):
    task_type = "provide_liquidity"

    async def build_transaction_params(self, nonce: int) -> Dict:
        params = self.task_config.parameters or {}
        router_address = params.get("router_address")
        if not router_address:
            raise ValueError("Missing router_address in task config parameters")

        token_a = self.task_config.token_in
        token_b = self.task_config.token_out
        amount = self.randomize_amount()

        addr_a, dec_a = await self._get_token_info(token_a)
        addr_b, dec_b = await self._get_token_info(token_b)
        is_native_a = addr_a is None

        amount_a = int(amount * (10 ** dec_a))
        amount_b = int(amount * (10 ** dec_b))
        slippage = self.task_config.slippage_tolerance or 0.005
        deadline = int(time.time()) + (self.task_config.deadline_mins or 20) * 60
        gas_price = int(
            await self.w3.eth.gas_price
            * float(self.wallet.persona.get("gas_multiplier", 1.0))
        )

        if not is_native_a:
            self.needs_approval = True
            self.token_in_address = Web3.to_checksum_address(addr_a)
            self.spender_address = Web3.to_checksum_address(router_address)
            self.amount_to_spend = amount_a

        if is_native_a:
            abi = [{
                "inputs": [
                    {"name": "token", "type": "address"},
                    {"name": "amountTokenDesired", "type": "uint256"},
                    {"name": "amountTokenMin", "type": "uint256"},
                    {"name": "amountETHMin", "type": "uint256"},
                    {"name": "to", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                ],
                "name": "addLiquidityETH",
                "outputs": [
                    {"name": "", "type": "uint256"},
                    {"name": "", "type": "uint256"},
                    {"name": "", "type": "uint256"},
                ],
                "type": "function",
            }]
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address), abi=abi
            )
            return contract.functions.addLiquidityETH(
                Web3.to_checksum_address(addr_b),
                amount_b,
                int(amount_b * (1 - slippage)),
                int(amount_a * (1 - slippage)),
                self.wallet.address,
                deadline,
            ).build_transaction({
                "from": self.wallet.address,
                "value": amount_a,
                "gas": params.get("gas_limit", 300000),
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
            })
        else:
            abi = [{
                "inputs": [
                    {"name": "tokenA", "type": "address"},
                    {"name": "tokenB", "type": "address"},
                    {"name": "amountADesired", "type": "uint256"},
                    {"name": "amountBDesired", "type": "uint256"},
                    {"name": "amountAMin", "type": "uint256"},
                    {"name": "amountBMin", "type": "uint256"},
                    {"name": "to", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                ],
                "name": "addLiquidity",
                "outputs": [],
                "type": "function",
            }]
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address), abi=abi
            )
            return contract.functions.addLiquidity(
                Web3.to_checksum_address(addr_a),
                Web3.to_checksum_address(addr_b),
                amount_a,
                amount_b,
                int(amount_a * (1 - slippage)),
                int(amount_b * (1 - slippage)),
                self.wallet.address,
                deadline,
            ).build_transaction({
                "from": self.wallet.address,
                "value": 0,
                "gas": params.get("gas_limit", 300000),
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
            })

    async def _get_token_info(self, symbol: Optional[str]) -> Tuple[Optional[str], int]:
        if not symbol:
            return None, 18
        if (
            symbol.upper() == self.chain.gas_token_symbol.upper()
            and self.chain.gas_token_is_native
        ):
            return None, 18
        from sqlalchemy import select
        from backend.models import ChainToken
        result = await self.db.execute(
            select(ChainToken).where(
                ChainToken.chain_id == self.chain.id, ChainToken.symbol == symbol
            )
        )
        token = result.scalar_one_or_none()
        if not token:
            raise ValueError(f"Token {symbol} not in registry for chain {self.chain.name}")
        return token.contract_address, token.decimals

    async def estimate_gas(self) -> Decimal:
        gas_price = await self.w3.eth.gas_price
        return Decimal(300000) * Decimal(gas_price)


class RemoveLiquidityTask(ProvideLiquidityTask):
    task_type = "remove_liquidity"

    async def build_transaction_params(self, nonce: int) -> Dict:
        params = self.task_config.parameters or {}
        router_address = params.get("router_address")
        if not router_address:
            raise ValueError("Missing router_address in task config parameters")

        token_a = self.task_config.token_in
        token_b = self.task_config.token_out
        lp_token_address = params.get("lp_token_address")
        if not lp_token_address:
            raise ValueError("Missing lp_token_address in task config parameters")

        amount = self.randomize_amount()
        lp_decimals = 18
        lp_amount = int(amount * (10 ** lp_decimals))
        slippage = self.task_config.slippage_tolerance or 0.005
        deadline = int(time.time()) + (self.task_config.deadline_mins or 20) * 60
        gas_price = int(
            await self.w3.eth.gas_price
            * float(self.wallet.persona.get("gas_multiplier", 1.0))
        )

        # Approve LP token
        self.needs_approval = True
        self.token_in_address = Web3.to_checksum_address(lp_token_address)
        self.spender_address = Web3.to_checksum_address(router_address)
        self.amount_to_spend = lp_amount

        addr_a, _ = await self._get_token_info(token_a)
        addr_b, _ = await self._get_token_info(token_b)

        if addr_a is None:
            abi = [{
                "inputs": [
                    {"name": "token", "type": "address"},
                    {"name": "liquidity", "type": "uint256"},
                    {"name": "amountTokenMin", "type": "uint256"},
                    {"name": "amountETHMin", "type": "uint256"},
                    {"name": "to", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                ],
                "name": "removeLiquidityETH",
                "outputs": [],
                "type": "function",
            }]
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address), abi=abi
            )
            return contract.functions.removeLiquidityETH(
                Web3.to_checksum_address(addr_b),
                lp_amount, 0, 0, self.wallet.address, deadline
            ).build_transaction({
                "from": self.wallet.address,
                "value": 0,
                "gas": params.get("gas_limit", 300000),
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
            })
        else:
            abi = [{
                "inputs": [
                    {"name": "tokenA", "type": "address"},
                    {"name": "tokenB", "type": "address"},
                    {"name": "liquidity", "type": "uint256"},
                    {"name": "amountAMin", "type": "uint256"},
                    {"name": "amountBMin", "type": "uint256"},
                    {"name": "to", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                ],
                "name": "removeLiquidity",
                "outputs": [],
                "type": "function",
            }]
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address), abi=abi
            )
            return contract.functions.removeLiquidity(
                Web3.to_checksum_address(addr_a),
                Web3.to_checksum_address(addr_b),
                lp_amount, 0, 0, self.wallet.address, deadline
            ).build_transaction({
                "from": self.wallet.address,
                "value": 0,
                "gas": params.get("gas_limit", 300000),
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
            })
