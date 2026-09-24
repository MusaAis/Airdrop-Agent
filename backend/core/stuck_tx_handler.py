import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from backend.database import async_session
from backend.models import Transaction

logger = logging.getLogger("airdrop.stuck")


async def handle_stuck_tx(task, tx_hash) -> None:
    """Detect if tx pending > 5 minutes, attempt speed up or cancel."""
    async with async_session() as db:
        result = await db.execute(
            select(Transaction).where(Transaction.tx_hash == tx_hash.hex())
        )
        tx_record = result.scalar_one_or_none()
        if not tx_record:
            logger.warning(f"Stuck tx {tx_hash.hex()} not found in DB")
            return

        tx_record_created_at = tx_record.created_at
        if tx_record_created_at.tzinfo is None:
            tx_record_created_at = tx_record_created_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - tx_record_created_at).total_seconds()
        if age <= 300:
            return  # not stuck yet

        logger.warning(f"Stuck tx {tx_hash.hex()} age={age:.0f}s — attempting speed up")

        try:
            old_tx = await task.w3.eth.get_transaction(tx_hash)
            # Build speed-up tx: same nonce, same data, 20% higher gas
            new_tx = {
                'nonce': old_tx['nonce'],
                'to': old_tx['to'],
                'value': old_tx['value'],
                'data': old_tx.get('input', '0x'),
                'gas': old_tx['gas'],
                'gasPrice': int(old_tx['gasPrice'] * 1.2),
                'chainId': task.chain.chain_id,
            }
            signed = await task.sign_transaction(new_tx)
            new_hash = await task.w3.eth.send_raw_transaction(signed.rawTransaction)
            tx_record.status = "replaced"
            tx_record.tx_hash = new_hash.hex()
            await db.commit()
            logger.info(f"Speed-up tx sent: {new_hash.hex()}")

        except Exception as e:
            logger.error(f"Speed up failed: {e} — attempting cancel")
            try:
                old_tx = await task.w3.eth.get_transaction(tx_hash)
                cancel_tx = {
                    'nonce': old_tx['nonce'],
                    'to': task.wallet.address,
                    'value': 0,
                    'data': '0x',
                    'gas': 21000,
                    'gasPrice': int(old_tx['gasPrice'] * 1.5),
                    'chainId': task.chain.chain_id,
                }
                signed = await task.sign_transaction(cancel_tx)
                cancel_hash = await task.w3.eth.send_raw_transaction(signed.rawTransaction)
                tx_record.status = "cancelled"
                await db.commit()
                logger.info(f"Cancel tx sent: {cancel_hash.hex()} for nonce {old_tx['nonce']}")
            except Exception as e2:
                logger.error(f"Cancel also failed: {e2}")
                tx_record.status = "stuck"
                await db.commit()
