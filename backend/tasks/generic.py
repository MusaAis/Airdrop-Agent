from backend.tasks.base import BaseTask
from typing import Dict

class InteractContractTask(BaseTask):
    task_type = "interact_contract"
    # Implement using contract address and encoded function data from task config
    async def build_transaction_params(self, nonce: int) -> Dict:
        # Extract params from task_config.parameters
        params = self.task_config.parameters or {}
        to_addr = params.get("contract_address")
        data = params.get("data", "0x")
        return {
            'to': to_addr,
            'data': data,
            'value': self.w3.to_wei(params.get("value_eth", 0), 'ether'),
            'gas': params.get("gas_limit", 300000),
            'gasPrice': await self.w3.eth.gas_price,
            'nonce': nonce,
            'chainId': self.chain.chain_id,
        }
