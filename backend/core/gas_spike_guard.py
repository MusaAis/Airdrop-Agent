import asyncio
import logging
from backend.chains.gas import get_current_gas_price, get_6h_average_gas, is_gas_spike
from backend.models import Chain
from backend.chains.rpc_pool import get_web3

logger = logging.getLogger("airdrop.gas_spike")

async def check_gas_spike(chain: Chain, multiplier: float = 3.0) -> bool:
    """Return True if a gas spike is detected."""
    w3 = await get_web3(chain)
    current = await get_current_gas_price(w3)
    avg = await get_6h_average_gas(chain.id, w3)
    spike = is_gas_spike(current, avg, multiplier)
    if spike:
        logger.warning(f"Gas spike on {chain.name}: {current} vs avg {avg}")
    return spike
