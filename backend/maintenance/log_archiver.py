import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import async_session
from backend.models import Log, LogsArchive, RPCLog

logger = logging.getLogger("airdrop.log_archiver")

LOG_RETENTION_DAYS = 90
RPC_LOG_RETENTION_DAYS = 7
BATCH_SIZE = 500


async def archive_old_logs() -> int:
    """Move logs older than 90 days to logs_archive table. Returns count archived."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)
    total_archived = 0

    async with async_session() as db:
        while True:
            result = await db.execute(
                select(Log).where(Log.created_at < cutoff).limit(BATCH_SIZE)
            )
            old_logs = result.scalars().all()

            if not old_logs:
                break

            for log in old_logs:
                archive = LogsArchive(
                    wallet_id=log.wallet_id,
                    chain_id=log.chain_id,
                    task_config_id=log.task_config_id,
                    project_id=log.project_id,
                    task_name=log.task_name,
                    tx_hash=log.tx_hash,
                    status=log.status,
                    error_message=log.error_message,
                    gas_used=log.gas_used,
                    gas_cost_usd=log.gas_cost_usd,
                    is_dry_run=log.is_dry_run,
                    created_at=log.created_at,
                )
                db.add(archive)
                await db.delete(log)

            await db.commit()
            total_archived += len(old_logs)
            logger.info(f"Archived batch of {len(old_logs)} logs")

    if total_archived:
        logger.info(f"Total archived: {total_archived} logs older than {LOG_RETENTION_DAYS} days")
    return total_archived


async def purge_rpc_logs() -> int:
    """Delete RPC request logs older than 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RPC_LOG_RETENTION_DAYS)
    total = 0

    async with async_session() as db:
        while True:
            result = await db.execute(
                select(RPCLog).where(RPCLog.created_at < cutoff).limit(BATCH_SIZE)
            )
            old = result.scalars().all()
            if not old:
                break
            for r in old:
                await db.delete(r)
            await db.commit()
            total += len(old)

    if total:
        logger.info(f"Purged {total} RPC log entries older than {RPC_LOG_RETENTION_DAYS} days")
    return total


async def run_all_maintenance() -> dict:
    """Run all maintenance jobs. Call this from APScheduler weekly."""
    logs_count = await archive_old_logs()
    rpc_count = await purge_rpc_logs()
    return {"logs_archived": logs_count, "rpc_logs_purged": rpc_count}
