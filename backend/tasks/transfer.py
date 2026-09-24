import logging
from decimal import Decimal
from typing import Dict, Optional
from web3 import Web3
from backend.tasks.base import BaseTask

logger = logging.getLogger("airdrop.tasks.transfer")


class TransferTask(BaseTask):
    task_type = "transfer"

    async def build_transaction_params(self, nonce: int) -> Dict:
        params = self.task_config.parameters or {}
        to_address = params.get("to_address", self.wallet.address)
        token = self.task_config.token_in
        amount = self.randomize_amount()
        gas_price = int(
            await self.w3.eth.gas_price
            * float(self.wallet.persona.get("gas_multiplier", 1.0))
        )

        is_native = (
            not token
            or (
                token.upper() == self.chain.gas_token_symbol.upper()
                and self.chain.gas_token_is_native
            )
        )

        if is_native:
            amount_wei = int(amount * (10 ** 18))
            return {
                "to": Web3.to_checksum_address(to_address),
                "value": amount_wei,
                "gas": 21000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
            }
        else:
            token_address, decimals = await self._get_token_info(token)
            amount_units = int(amount * (10 ** decimals))
            abi = [{
                "inputs": [
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"},
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function",
            }]
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address), abi=abi
            )
            return contract.functions.transfer(
                Web3.to_checksum_address(to_address), amount_units
            ).build_transaction({
                "from": self.wallet.address,
                "gas": 65000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.chain.chain_id,
            })

    async def _get_token_info(self, symbol: str):
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
        return token.contract_address, token.decimals

    async def estimate_gas(self) -> Decimal:
        gas_price = await self.w3.eth.gas_price
        return Decimal(65000) * Decimal(gas_price)
