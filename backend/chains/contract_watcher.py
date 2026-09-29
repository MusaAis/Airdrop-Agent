import asyncio, logging
from web3 import AsyncWeb3
from backend.models import ProjectContract
from backend.database import async_session
from backend.chains.manager import get_chain
from backend.chains.rpc_pool import get_web3

logger = logging.getLogger("airdrop.contract_watcher")

async def check_bytecode_changes():
    async with async_session() as db:
        from sqlalchemy import select
        contracts = (await db.execute(select(ProjectContract))).scalars().all()
        for c in contracts:
            if not c.bytecode_hash:
                continue
            try:
                chain = await get_chain(db, c.chain_id)
                w3 = await get_web3(chain)
                code = await w3.eth.get_code(c.address)
                current_hash = w3.keccak(code).hex()
                if current_hash != c.bytecode_hash:
                    logger.warning(f"Contract upgraded: {c.label} ({c.address})")
            except Exception as e:
                logger.error(f"Bytecode check failed: {e}")


async def check_all_contracts(db=None):
    """Phase 5 fix: scheduler._run_contract_check imports this name, which did
    not exist, so the 4-hourly job failed on import every time. Thin wrapper;
    the db argument is accepted for the scheduler's call signature only —
    check_bytecode_changes opens its own session."""
    await check_bytecode_changes()
