"""
APScheduler setup for all periodic background jobs:
- Faucet auto-trigger (every 30 minutes)
- Sybil re-scoring (randomized 6-18h interval, re-rolled each cycle)
- Log archival (weekly)
- Daily summary Telegram report (every day at 08:00 UTC)
- Gas history sampling (every 10 minutes)
- Contract upgrade check (every 4 hours)

Discovery scanning and encrypted DB backups were removed (see PLAN.md).
"""

import logging
import random
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger("airdrop.scheduler")

# Sybil re-score runs on a randomized interval instead of a fixed one, so the
# timing itself doesn't become a predictable pattern. Re-rolled every cycle.
SYBIL_RESCORE_MIN_HOURS = 6
SYBIL_RESCORE_MAX_HOURS = 18

_scheduler: AsyncIOScheduler = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def _run_faucet_check():
    try:
        from backend.database import async_session
        from backend.models import Wallet, Chain
        from backend.faucet.manager import request_faucet_for_wallet
        from backend.chains.rpc_pool import get_web3
        from backend.wallet.balance import get_gas_token_balance
        from sqlalchemy import select

        async with async_session() as db:
            wallets = (await db.execute(
                select(Wallet).where(Wallet.status == "active", Wallet.is_gas_wallet == False)
            )).scalars().all()
            chains = (await db.execute(
                select(Chain).where(Chain.enabled == True)
            )).scalars().all()

            for wallet in wallets:
                for chain in chains:
                    try:
                        bal = await get_gas_token_balance(chain, wallet.address)
                        if bal < chain.min_gas_balance_warning:
                            await request_faucet_for_wallet(wallet, chain, db)
                    except Exception as e:
                        logger.debug(f"Faucet check skip {wallet.address}/{chain.name}: {e}")
    except Exception as e:
        logger.error(f"Faucet scheduler error: {e}")


async def _run_sybil_rescore():
    """
    Run one Sybil re-score cycle, then immediately schedule the next one at a
    freshly randomized 6-18h delay (see PLAN.md §6). Self-rescheduling via a
    one-shot DateTrigger instead of a fixed IntervalTrigger, so the interval
    itself changes every cycle rather than repeating on a predictable clock.
    """
    try:
        from backend.database import async_session
        from backend.wallet.sybil_detector import compute_wallet_correlations
        from backend.ai.orchestrator import dual_ai_validate
        from backend.ai.prompts import prompt_sybil
        async with async_session() as db:
            pairs = await compute_wallet_correlations(db)
            if pairs:
                validation = await dual_ai_validate(
                    task_type="sybil",
                    system_prompt="You are a blockchain forensics analyst specializing in Sybil detection.",
                    user_prompt=prompt_sybil(str(pairs)),
                    db=db,
                )
                high = [p for p in pairs if p.get("correlation_score", 0) >= 60]
                if high and validation.agreement_score >= 60:
                    from backend.telegram.alerts import create_and_send_alert
                    await create_and_send_alert(
                        type="sybil_flag",
                        severity="warning",
                        message=f"⚠️ Sybil re-score: {len(high)} high-risk wallet pairs detected "
                                f"(AI agreement {validation.agreement_score}%). Use /report_sybil for details."
                    )
    except Exception as e:
        logger.error(f"Sybil rescore error: {e}")
    finally:
        _schedule_next_sybil_rescore()


def _schedule_next_sybil_rescore():
    """Pick a fresh random delay (6-18h) and schedule the next sybil re-score
    run as a one-shot job. Called once at startup and again at the end of
    every run, so the job perpetually re-schedules itself."""
    sched = get_scheduler()
    delay_hours = random.uniform(SYBIL_RESCORE_MIN_HOURS, SYBIL_RESCORE_MAX_HOURS)
    run_at = datetime.now(timezone.utc) + timedelta(hours=delay_hours)
    sched.add_job(
        _run_sybil_rescore,
        DateTrigger(run_date=run_at),
        id="sybil_rescore",
        replace_existing=True,
    )
    logger.info(f"Next sybil re-score scheduled in {delay_hours:.1f}h (at {run_at.isoformat()})")

async def _run_log_archival():
    try:
        from backend.maintenance.log_archiver import run_all_maintenance
        result = await run_all_maintenance()
        logger.info(f"Log archival: {result}")
    except Exception as e:
        logger.error(f"Log archival error: {e}")


async def _run_daily_summary():
    try:
        from backend.telegram.alerts import send_daily_summary
        await send_daily_summary()
    except Exception as e:
        logger.error(f"Daily summary error: {e}")


async def _run_gas_sample():
    try:
        from backend.database import async_session
        from backend.models import Chain
        from backend.chains.rpc_pool import get_web3
        from backend.chains.gas import sample_gas_price
        from sqlalchemy import select
        async with async_session() as db:
            chains = (await db.execute(select(Chain).where(Chain.enabled == True))).scalars().all()
        for chain in chains:
            try:
                w3 = await get_web3(chain)
                await sample_gas_price(chain.id, w3)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Gas sample error: {e}")


async def _run_contract_check():
    try:
        from backend.database import async_session
        from backend.chains.contract_watcher import check_all_contracts
        async with async_session() as db:
            await check_all_contracts(db)
    except Exception as e:
        logger.error(f"Contract check error: {e}")


def start_scheduler():
    sched = get_scheduler()

    sched.add_job(_run_faucet_check,   IntervalTrigger(minutes=30),  id="faucet_check",    replace_existing=True)
    sched.add_job(_run_log_archival,   CronTrigger(day_of_week="sun", hour=3), id="log_archival", replace_existing=True)
    sched.add_job(_run_daily_summary,  CronTrigger(hour=8, minute=0), id="daily_summary",   replace_existing=True)
    sched.add_job(_run_gas_sample,     IntervalTrigger(minutes=10),  id="gas_sample",       replace_existing=True)
    sched.add_job(_run_contract_check, IntervalTrigger(hours=4),     id="contract_check",   replace_existing=True)

    if not sched.running:
        sched.start()
        logger.info("APScheduler started with all jobs")

    # Sybil re-score is self-rescheduling (randomized interval) rather than a
    # fixed IntervalTrigger — kick off its first cycle here.
    _schedule_next_sybil_rescore()

    return sched


def stop_scheduler():
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("APScheduler stopped")

