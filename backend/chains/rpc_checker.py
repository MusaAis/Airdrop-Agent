import asyncio
import time
from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider
from backend.models import Chain

async def test_rpc_endpoint(url: str) -> dict:
    start = time.time()
    try:
        provider = AsyncHTTPProvider(url)
        w3 = AsyncWeb3(provider)
        block = await w3.eth.block_number
        latency = (time.time() - start) * 1000
        return {"url": url, "status": "ok", "latency_ms": latency, "block": block}
    except Exception as e:
        return {"url": url, "status": "error", "error": str(e)}

async def check_all_rpcs(chain: Chain) -> list:
    results = []
    for url in chain.rpc_urls:
        results.append(await test_rpc_endpoint(url))
    return results
