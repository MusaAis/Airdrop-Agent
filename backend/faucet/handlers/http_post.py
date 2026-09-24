import httpx
import json
import logging
from backend.faucet.handlers.base import BaseFaucetHandler
from backend.proxy_manager import get_assigned_proxy

logger = logging.getLogger("airdrop.faucet.http_post")

class HttpPostFaucetHandler(BaseFaucetHandler):
    async def request(self, url: str, wallet_address: str, template: dict, wallet_id: int = None) -> dict:
        body = json.dumps(template).replace("{address}", wallet_address)
        proxy = None
        if wallet_id:
            proxy = await get_assigned_proxy(wallet_id)
        async with httpx.AsyncClient(proxies=proxy, timeout=30) as client:
            resp = await client.post(url, content=body, headers={"Content-Type": "application/json"})
            return {"status": resp.status_code, "text": resp.text}
