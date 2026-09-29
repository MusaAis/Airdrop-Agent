"""Async transaction confirmation monitor loop (used by agent)."""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Transaction
from backend.database import async_session
from backend.chains.rpc_pool import get_web3
from backend.chains.manager import get_chain

logger = logging.getLogger("airdrop.tx_monitor")

async def monitor_pending_transactions():
    """Background task: check pending txs and update status.

    Phase 5 fix: datetime/timezone/select were used but never imported, so
    the NameError was swallowed by the except below and no pending
    transaction was ever updated.
    """
    async with async_session() as db:
        result = await db.execute(select(Transaction).where(Transaction.status == "pending"))
        pending = result.scalars().all()
        for tx in pending:
            try:
                chain = await get_chain(db, tx.chain_id)
                w3 = await get_web3(chain)
                receipt = await w3.eth.get_transaction_receipt(tx.tx_hash)
                if receipt:
                    tx.status = "confirmed" if receipt.status == 1 else "failed"
                    if receipt.status != 1 and not tx.error_message:
                        tx.error_message = "reverted on-chain (detected by monitor)"
                    tx.confirmed_at = datetime.now(timezone.utc)
                    tx.block_number = receipt.blockNumber
                    tx.gas_used = receipt.gasUsed
                    await db.commit()
                    logger.info(f"TX {tx.tx_hash} updated to {tx.status}")
            except Exception as e:
                # A missing receipt (tx still pending) raises here on most RPCs — expected.
                logger.debug(f"Monitor: {tx.tx_hash} not resolved yet: {e}")
