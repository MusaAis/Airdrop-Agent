import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import WalletNonce

logger = logging.getLogger("airdrop.nonce")

LOCK_WAIT_TIMEOUT_SECS = 30
LOCK_POLL_INTERVAL_SECS = 0.5


async def get_nonce(db: AsyncSession, wallet_id: int, chain_id: int) -> WalletNonce:
    result = await db.execute(
        select(WalletNonce).where(
            WalletNonce.wallet_id == wallet_id,
            WalletNonce.chain_id == chain_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        record = WalletNonce(wallet_id=wallet_id, chain_id=chain_id, nonce=0)
        db.add(record)
        await db.commit()
        await db.refresh(record)
    return record


ONCHAIN_NONCE_TIMEOUT_SECS = 15


async def _pending_onchain_nonce(db: AsyncSession, wallet_id: int, chain_id: int) -> int:
    """Next usable nonce according to the chain (counts txs still in the mempool)."""
    from web3 import Web3
    from backend.models import Wallet, Chain
    from backend.chains.rpc_pool import get_web3
    wallet = await db.get(Wallet, wallet_id)
    chain = await db.get(Chain, chain_id)
    if wallet is None or chain is None:
        raise ValueError("wallet or chain not found")
    w3 = await get_web3(chain)
    return await asyncio.wait_for(
        w3.eth.get_transaction_count(Web3.to_checksum_address(wallet.address), "pending"),
        timeout=ONCHAIN_NONCE_TIMEOUT_SECS,
    )


async def lock_nonce(db: AsyncSession, wallet_id: int, chain_id: int) -> int:
    """
    Lock and return the current nonce.
    Waits up to LOCK_WAIT_TIMEOUT_SECS if the nonce is already locked
    by another concurrent task. Raises TimeoutError if lock not obtained.
    """
    deadline = asyncio.get_event_loop().time() + LOCK_WAIT_TIMEOUT_SECS

    while True:
        await db.rollback()          # ensure fresh read each iteration
        record = await get_nonce(db, wallet_id, chain_id)

        if not record.locked:
            record.locked = True
            record.locked_at = datetime.now(timezone.utc)
            await db.commit()
            # A new record starts at 0 and the stored value can fall behind the chain
            # (wallet used elsewhere, funded wallet with history, replaced txs). Sending
            # a stale nonce fails with "nonce too low", so never go below the chain's
            # pending count. If the RPC read fails we keep the stored value: the tx then
            # fails harmlessly instead of being sent with a guessed nonce.
            try:
                onchain = await _pending_onchain_nonce(db, wallet_id, chain_id)
                if onchain > record.nonce:
                    logger.info(
                        f"Nonce raised to chain value: wallet={wallet_id} chain={chain_id} "
                        f"stored={record.nonce} onchain={onchain}"
                    )
                    record.nonce = onchain
                    await db.commit()
            except Exception as e:
                await db.rollback()
                logger.warning(f"Could not read on-chain nonce (wallet={wallet_id} chain={chain_id}): {e}")
                record = await get_nonce(db, wallet_id, chain_id)
            logger.debug(f"Nonce locked: wallet={wallet_id} chain={chain_id} nonce={record.nonce}")
            return record.nonce

        # Check if lock is stale (held > 10 minutes → auto-release)
        if record.locked_at:
            record_locked_at = record.locked_at
            if record_locked_at.tzinfo is None:
                record_locked_at = record_locked_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - record_locked_at).total_seconds()
            if age > 600:
                logger.warning(
                    f"Stale nonce lock for wallet={wallet_id} chain={chain_id} "
                    f"(held {age:.0f}s) — force releasing"
                )
                record.locked = False
                await db.commit()
                continue

        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(
                f"Could not acquire nonce lock for wallet={wallet_id} "
                f"chain={chain_id} within {LOCK_WAIT_TIMEOUT_SECS}s"
            )

        logger.debug(f"Nonce locked by another task (wallet={wallet_id}), waiting…")
        await asyncio.sleep(LOCK_POLL_INTERVAL_SECS)


async def release_nonce(
    db: AsyncSession, wallet_id: int, chain_id: int, increment: bool = True
):
    record = await get_nonce(db, wallet_id, chain_id)
    record.locked = False
    record.locked_at = None
    if increment:
        record.nonce += 1
    await db.commit()
    logger.debug(
        f"Nonce released: wallet={wallet_id} chain={chain_id} "
        f"nonce={record.nonce} incremented={increment}"
    )


async def sync_nonce_from_chain(
    db: AsyncSession, wallet_id: int, chain_id: int, onchain_nonce: int
):
    record = await get_nonce(db, wallet_id, chain_id)
    record.nonce = onchain_nonce
    record.locked = False
    record.locked_at = None
    await db.commit()
    logger.info(f"Nonce synced from chain: wallet={wallet_id} chain={chain_id} nonce={onchain_nonce}")

