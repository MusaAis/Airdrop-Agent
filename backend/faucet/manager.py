import asyncio
import json
import logging
import httpx
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Faucet, FaucetToken, FaucetRequest, Wallet, Chain
from backend.database import async_session
from backend.proxy_manager import get_assigned_proxy, client_proxy_kwargs

logger = logging.getLogger("airdrop.faucet")


async def _make_faucet_request(
    url: str, wallet_address: str, body_template: dict, fallback_urls: List[str] = None,
    wallet_id: Optional[int] = None, method: str = "POST",
) -> dict:
    """Make real HTTP POST to faucet, try fallback URLs on failure.

    Phase 7: if the wallet has an active proxy assigned, the request goes through
    it (a dead proxy fails the request rather than leaking the server's own IP,
    which would link every wallet to one address)."""
    urls_to_try = [url] + (fallback_urls or [])
    body = json.dumps(body_template).replace("{address}", wallet_address)

    proxy_kwargs = {}
    if wallet_id is not None:
        assigned = await get_assigned_proxy(wallet_id)
        if assigned:
            proxy_kwargs = client_proxy_kwargs(assigned["https"])

    for try_url in urls_to_try:
        try:
            async with httpx.AsyncClient(timeout=30, **proxy_kwargs) as client:
                if (method or "POST").upper() == "GET":
                    params = {k: str(v).replace("{address}", wallet_address) for k, v in (body_template or {}).items()}
                    resp = await client.get(
                        try_url.replace("{address}", wallet_address),
                        params=params,
                        headers={"User-Agent": "AirdropAgent/1.0"},
                    )
                else:
                    resp = await client.post(
                        try_url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "AirdropAgent/1.0",
                        },
                    )
                if resp.status_code in (200, 201, 202):
                    logger.info(f"Faucet success: {try_url} → {resp.status_code}")
                    return {"success": True, "url": try_url, "response": resp.text[:300]}
                else:
                    logger.warning(
                        f"Faucet {try_url} returned {resp.status_code}: {resp.text[:150]}"
                    )
        except httpx.TimeoutException:
            logger.warning(f"Faucet {try_url} timed out")
        except Exception as e:
            logger.error(f"Faucet {try_url} error: {e}")

    return {"success": False, "error": "All faucet URLs failed"}


async def request_faucet_for_wallet(
    wallet: Wallet, chain: Chain, db: Optional[AsyncSession] = None
) -> List[dict]:
    """Trigger faucet for all available tokens on a chain for a wallet."""
    if db is None:
        async with async_session() as session:
            return await _do_request(wallet, chain, session)
    return await _do_request(wallet, chain, db)


async def _do_request(wallet: Wallet, chain: Chain, db: AsyncSession) -> List[dict]:
    faucets_result = await db.execute(
        select(Faucet).where(Faucet.chain_id == chain.id, Faucet.enabled == True)
    )
    faucets = faucets_result.scalars().all()

    if not faucets:
        return [{"status": "no_faucets", "message": f"No faucets configured for {chain.name}"}]

    results = []
    for faucet in faucets:
        # Check cooldown
        last_result = await db.execute(
            select(FaucetRequest)
            .where(
                FaucetRequest.wallet_id == wallet.id,
                FaucetRequest.faucet_id == faucet.id,
            )
            .order_by(FaucetRequest.requested_at.desc())
            .limit(1)
        )
        last_req = last_result.scalar_one_or_none()

        if last_req:
            req_at = last_req.requested_at
            if req_at.tzinfo is None:
                req_at = req_at.replace(tzinfo=timezone.utc)
            hours_since = (
                datetime.now(timezone.utc) - req_at
            ).total_seconds() / 3600
            if hours_since < faucet.cooldown_hours:
                remaining = round(faucet.cooldown_hours - hours_since, 1)
                results.append({
                    "faucet": faucet.name,
                    "status": "cooldown",
                    "remaining_hours": remaining,
                })
                continue

        # Make real HTTP request
        body_template = faucet.body_template or {"address": "{address}"}
        fallback_urls = faucet.fallback_urls if isinstance(faucet.fallback_urls, list) else []
        request_result = await _make_faucet_request(
            faucet.url, wallet.address, body_template, fallback_urls, wallet_id=wallet.id,
            method=faucet.method,
        )

        # Get tokens this faucet provides
        tokens_result = await db.execute(
            select(FaucetToken).where(FaucetToken.faucet_id == faucet.id)
        )
        tokens = tokens_result.scalars().all()
        received = (
            [{"symbol": t.token_symbol, "amount": t.amount_given} for t in tokens]
            if request_result["success"]
            else []
        )

        # Log in DB
        req = FaucetRequest(
            wallet_id=wallet.id,
            faucet_id=faucet.id,
            requested_at=datetime.now(timezone.utc),
            tokens_received=received,
            status="success" if request_result["success"] else "failed",
            trigger_type="manual",
            error_message=request_result.get("error"),
        )
        db.add(req)
        await db.commit()

        results.append({
            "faucet": faucet.name,
            "status": "success" if request_result["success"] else "failed",
            "tokens": received,
            "error": request_result.get("error"),
        })

    return results


async def auto_gas_refill(wallet: Wallet, chain: Chain, db: AsyncSession) -> bool:
    """If wallet gas balance below warning, send from designated gas wallet."""
    from backend.wallet.balance import get_gas_token_balance

    balance = await get_gas_token_balance(chain, wallet.address)
    if balance >= Decimal(str(chain.min_gas_balance_warning)):
        return True  # already fine

    gas_wallet_result = await db.execute(
        select(Wallet)
        .where(Wallet.is_gas_wallet == True, Wallet.status == "active")
        .limit(1)
    )
    gas_wallet = gas_wallet_result.scalar_one_or_none()

    if not gas_wallet:
        logger.warning(f"No gas wallet available for refill of {wallet.address}")
        return False

    logger.info(
        f"Gas refill needed: {wallet.address} on {chain.name} "
        f"(balance={balance}, threshold={chain.min_gas_balance_warning})"
    )
    # Actual transfer executed via TransferTask when available
    # For now trigger faucet as primary method
    await request_faucet_for_wallet(wallet, chain, db)
    return True
