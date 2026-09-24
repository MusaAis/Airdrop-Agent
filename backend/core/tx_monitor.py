"""Async transaction confirmation monitor loop (used by agent)."""
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Transaction
from backend.database import async_session
from backend.chains.rpc_pool import get_web3
from backend.chains.manager import get_chain

logger = logging.getLogger("airdrop.tx_monitor")

async def monitor_pending_transactions():
    """Background task: check pending txs and update status."""
    async with async_session() as db:
        # fetch pending transactions
        from sqlalchemy import select
        result = await db.execute(select(Transaction).where(Transaction.status == "pending"))
        pending = result.scalars().all()
        for tx in pending:
            try:
                chain = await get_chain(db, tx.chain_id)
                w3 = await get_web3(chain)
                receipt = await w3.eth.get_transaction_receipt(tx.tx_hash)
                if receipt:
                    tx.status = "confirmed" if receipt.status == 1 else "failed"
                    tx.confirmed_at = datetime.now(timezone.utc)
                    tx.block_number = receipt.blockNumber
                    tx.gas_used = receipt.gasUsed
                    await db.commit()
                    logger.info(f"TX {tx.tx_hash} updated to {tx.status}")
            except Exception as e:
                logger.error(f"Monitor error: {e}")
