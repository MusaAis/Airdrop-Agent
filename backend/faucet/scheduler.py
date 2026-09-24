"""
Faucet scheduler — runs as part of APScheduler jobs.
Two trigger modes:
  - threshold: wallet balance < min_gas_balance_warning → request now
  - scheduled: every N hours regardless of balance (claim all available tokens)
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Wallet, Chain, Faucet, FaucetRequest
from backend.database import async_session
from backend.faucet.manager import request_faucet_for_wallet
from backend.wallet.balance import get_gas_token_balance
from backend.telegram.alerts import create_and_send_alert

logger = logging.getLogger("airdrop.faucet.scheduler")


async def run_threshold_check():
    """
    Called every 30 minutes by APScheduler.
    Requests faucet for any wallet whose gas balance is below warning threshold.
    """
    async with async_session() as db:
        wallets = (
            await db.execute(
                select(Wallet).where(
                    Wallet.status == "active",
                    Wallet.is_gas_wallet == False,
                )
            )
        ).scalars().all()

        chains = (
            await db.execute(select(Chain).where(Chain.enabled == True))
        ).scalars().all()

        triggered = 0
        for wallet in wallets:
            for chain in chains:
                try:
                    balance = await get_gas_token_balance(chain, wallet.address)
                    if balance < chain.min_gas_balance_warning:
                        results = await request_faucet_for_wallet(wallet, chain, db)
                        for r in results:
                            if r.get("status") == "success":
                                triggered += 1
                                logger.info(
                                    f"Threshold faucet: {wallet.address[:10]}... "
                                    f"chain={chain.name}"
                                )
                except Exception as e:
                    logger.debug(
                        f"Threshold check skip {wallet.address[:8]}/{chain.name}: {e}"
                    )

        if triggered:
            logger.info(f"Threshold faucet run: {triggered} requests sent")


async def run_scheduled_faucet():
    """
    Called every 24 hours by APScheduler.
    Requests faucet for ALL active wallets on ALL chains that have faucets configured,
    respecting per-faucet cooldown periods.
    Logs results to Telegram if any failures.
    """
    async with async_session() as db:
        wallets = (
            await db.execute(
                select(Wallet).where(
                    Wallet.status == "active",
                    Wallet.is_gas_wallet == False,
                )
            )
        ).scalars().all()

        chains_with_faucets = (
            await db.execute(
                select(Chain)
                .join(Faucet, Faucet.chain_id == Chain.id)
                .where(Chain.enabled == True, Faucet.enabled == True)
                .distinct()
            )
        ).scalars().all()

        success_count = 0
        fail_count = 0
        cooldown_count = 0

        for wallet in wallets:
            for chain in chains_with_faucets:
                try:
                    results = await request_faucet_for_wallet(wallet, chain, db)
                    for r in results:
                        status = r.get("status", "unknown")
                        if status == "success":
                            success_count += 1
                        elif status == "cooldown":
                            cooldown_count += 1
                        else:
                            fail_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.error(
                        f"Scheduled faucet error {wallet.address[:8]}/{chain.name}: {e}"
                    )

        summary = (
            f"🚰 Scheduled faucet run complete\n"
            f"✅ Success: {success_count}\n"
            f"⏳ Cooldown: {cooldown_count}\n"
            f"❌ Failed: {fail_count}"
        )
        logger.info(summary)

        if fail_count > 0:
            await create_and_send_alert(
                type="faucet_failed",
                severity="warning",
                message=summary,
            )
