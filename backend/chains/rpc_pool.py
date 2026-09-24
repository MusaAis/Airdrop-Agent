import asyncio
import logging
from typing import Optional
from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider
from backend.models import Chain, RPCLog
from backend.database import async_session
from datetime import datetime, timezone

logger = logging.getLogger("airdrop.rpc_pool")

# in-memory connection cache (per chain_db_id)
_rpc_connections = {}
_rate_limiters = {}  # per chain_db_id: asyncio.Semaphore

async def get_web3(chain: Chain) -> AsyncWeb3:
    """Get a working Web3 connection for a chain, trying all RPC URLs."""
    if chain.id in _rpc_connections:
        w3 = _rpc_connections[chain.id]
        if await _test_connection(w3):
            return w3

    for url in chain.rpc_urls:
        try:
            provider = AsyncHTTPProvider(url)
            w3 = AsyncWeb3(provider)
            block = await w3.eth.block_number  # connectivity check
            _rpc_connections[chain.id] = w3
            logger.info(f"Connected to {chain.name} via {url}")
            return w3
        except Exception as e:
            logger.warning(f"RPC {url} failed: {e}")
            await _log_rpc_failure(chain.id, url, str(e))
    raise ConnectionError(f"All RPC endpoints failed for chain {chain.name}")

async def _test_connection(w3: AsyncWeb3) -> bool:
    try:
        await w3.eth.block_number
        return True
    except:
        return False

async def _log_rpc_failure(chain_db_id: int, url: str, error: str):
    async with async_session() as db:
        log = RPCLog(chain_id=chain_db_id, rpc_url=url, method="eth_blockNumber", status="failed", latency_ms=None)
        db.add(log)
        await db.commit()

def get_rate_limiter(chain: Chain) -> asyncio.Semaphore:
    if chain.id not in _rate_limiters:
        _rate_limiters[chain.id] = asyncio.Semaphore(chain.rpc_rate_limit_per_sec)
    return _rate_limiters[chain.id]
