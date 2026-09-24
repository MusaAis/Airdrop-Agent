import logging
from decimal import Decimal
from typing import Dict, Optional
from web3 import Web3
from backend.tasks.base import BaseTask

logger = logging.getLogger("airdrop.tasks.stake")


class StakeTask(BaseTask):
    task_type = "stake"

    async def build_transaction_params(self, nonce: int) -> Dict:
        params = self.task_config.parameters or {}
        staking_contract = params.get("staking_contract")
        if not staking_contract:
            raise ValueError("Missing staking_contract in task config parameters")

        stake_function = params.get("stake_function", "stake")
        token = self.task_config.token_in
        amount = self.randomize_amount()
        decimals = await self._get_decimals(token)
        amount_units = int(amount * (10 ** decimals))
        gas_price = int(
            await self.w3.eth.gas_price
            * float(self.wallet.persona.get("gas_multiplier", 1.0))
        )

        is_native_stake = (
            not token
            or (
                token.upper() == self.chain.gas_token_symbol.upper()
                and self.chain.gas_token_is_native
            )
        )

        if not is_native_stake:
            token_address = await self._resolve_token_address(token)
            self.needs_approval = True
            self.token_in_address = Web3.to_checksum_address(token_address)
            self.spender_address = Web3.to_checksum_address(staking_contract)
            self.amount_to_spend = amount_units

        abi = [{
            "inputs": [{"name": "amount", "type": "uint256"}],
            "name": stake_function,
            "outputs": [],
            "type": "function",
        }]
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(staking_contract), abi=abi
        )
        tx_data = contract.encode_abi(stake_function, [amount_units])

        return {
            "to": Web3.to_checksum_address(staking_contract),
            "data": tx_data,
            "value": amount_units if is_native_stake else 0,
            "gas": params.get("gas_limit", 200000),
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": self.chain.chain_id,
        }

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
        return Decimal(200000) * Decimal(gas_price)


class UnstakeTask(StakeTask):
    task_type = "unstake"

    async def build_transaction_params(self, nonce: int) -> Dict:
        params = self.task_config.parameters or {}
        staking_contract = params.get("staking_contract")
        if not staking_contract:
            raise ValueError("Missing staking_contract in task config parameters")

        unstake_function = params.get("unstake_function", "withdraw")
        token = self.task_config.token_in
        amount = self.randomize_amount()
        decimals = await self._get_decimals(token)
        amount_units = int(amount * (10 ** decimals))
        gas_price = int(
            await self.w3.eth.gas_price
            * float(self.wallet.persona.get("gas_multiplier", 1.0))
        )

        abi = [{
            "inputs": [{"name": "amount", "type": "uint256"}],
            "name": unstake_function,
            "outputs": [],
            "type": "function",
        }]
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(staking_contract), abi=abi
        )

        return {
            "to": Web3.to_checksum_address(staking_contract),
            "data": contract.encode_abi(unstake_function, [amount_units]),
            "value": 0,
            "gas": params.get("gas_limit", 200000),
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": self.chain.chain_id,
        }
