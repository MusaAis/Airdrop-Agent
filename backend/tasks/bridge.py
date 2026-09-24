import logging
import time
from decimal import Decimal
from typing import Dict, Optional
from web3 import Web3
from backend.tasks.base import BaseTask

logger = logging.getLogger("airdrop.tasks.bridge")


class BridgeTask(BaseTask):
    task_type = "bridge"

    async def build_transaction_params(self, nonce: int) -> Dict:
        params = self.task_config.parameters or {}
        bridge_contract = params.get("bridge_contract")
        dest_chain_id = params.get("dest_chain_id")

        if not bridge_contract:
            raise ValueError("Missing bridge_contract in task config parameters")
        if not dest_chain_id:
            raise ValueError("Missing dest_chain_id in task config parameters")

        token_in, token_out = self._resolve_direction()
        amount = self.randomize_amount()
        decimals = await self._get_decimals(token_in)
        amount_units = int(amount * (10 ** decimals))
        gas_price = int(
            await self.w3.eth.gas_price
            * float(self.wallet.persona.get("gas_multiplier", 1.0))
        )
        bridge_type = params.get("bridge_type", "erc20")

        if bridge_type == "native":
            return {
                "to": Web3.to_checksum_address(bridge_contract),
                "value": amount_units,
                "gas": params.get("gas_limit", 300000),
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
                "data": self._encode_bridge_data(params, dest_chain_id, amount_units),
            }
        else:
            # ERC20 bridge — approval needed
            token_address = await self._resolve_token_address(token_in)
            self.needs_approval = True
            self.token_in_address = Web3.to_checksum_address(token_address)
            self.spender_address = Web3.to_checksum_address(bridge_contract)
            self.amount_to_spend = amount_units

            bridge_fee = params.get("bridge_fee_wei", 0)
            return {
                "to": Web3.to_checksum_address(bridge_contract),
                "value": bridge_fee,
                "gas": params.get("gas_limit", 350000),
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
                "data": self._encode_bridge_data(
                    params, dest_chain_id, amount_units, token_address
                ),
            }

    def _encode_bridge_data(
        self,
        params: dict,
        dest_chain_id: int,
        amount: int,
        token: Optional[str] = None,
    ) -> str:
        bridge_function = params.get("bridge_function", "deposit")
        bridge_contract = params.get("bridge_contract")

        if bridge_function == "deposit" and token:
            abi = [{
                "name": "deposit",
                "type": "function",
                "inputs": [
                    {"name": "token", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "destChainId", "type": "uint16"},
                ],
            }]
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(bridge_contract), abi=abi
            )
            return contract.encode_abi(
                "deposit",
                [Web3.to_checksum_address(token), amount, dest_chain_id],
            )

        elif bridge_function == "sendNative":
            abi = [{
                "name": "sendNative",
                "type": "function",
                "inputs": [
                    {"name": "destChainId", "type": "uint16"},
                    {"name": "recipient", "type": "address"},
                ],
            }]
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(bridge_contract), abi=abi
            )
            return contract.encode_abi(
                "sendNative", [dest_chain_id, self.wallet.address]
            )

        # Fallback: use raw data from config
        return params.get("data", "0x")

    def _resolve_direction(self):
        import random
        if (
            self.task_config.bidirectional
            and self.task_config.token_in_reverse
            and random.random() < 0.5
        ):
            return self.task_config.token_in_reverse, self.task_config.token_out_reverse
        return self.task_config.token_in, self.task_config.token_out

    async def _resolve_token_address(self, symbol: str) -> str:
        from sqlalchemy import select
        from backend.models import ChainToken
        result = await self.db.execute(
            select(ChainToken).where(
                ChainToken.chain_id == self.chain.id, ChainToken.symbol == symbol
            )
        )
        token = result.scalar_one_or_none()
        if not token:
            raise ValueError(f"Token {symbol} not registered for chain {self.chain.name}")
        return token.contract_address

    async def _get_decimals(self, symbol: Optional[str]) -> int:
        if not symbol:
            return 18
        if (
            symbol.upper() == self.chain.gas_token_symbol.upper()
            and self.chain.gas_token_is_native
        ):
            return 18
        from sqlalchemy import select
        from backend.models import ChainToken
        result = await self.db.execute(
            select(ChainToken).where(
                ChainToken.chain_id == self.chain.id, ChainToken.symbol == symbol
            )
        )
        token = result.scalar_one_or_none()
        return token.decimals if token else 18

    async def estimate_gas(self) -> Decimal:
        gas_price = await self.w3.eth.gas_price
        return Decimal(350000) * Decimal(gas_price)
