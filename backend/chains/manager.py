from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Chain, ChainToken
from typing import List, Optional
import json

async def create_chain(db: AsyncSession, **kwargs) -> Chain:
    chain = Chain(**kwargs)
    db.add(chain)
    await db.commit()
    await db.refresh(chain)
    return chain

async def get_chain(db: AsyncSession, chain_db_id: int) -> Optional[Chain]:
    return await db.get(Chain, chain_db_id)

async def get_chain_by_chain_id(db: AsyncSession, chain_id: int) -> Optional[Chain]:
    result = await db.execute(select(Chain).where(Chain.chain_id == chain_id))
    return result.scalar_one_or_none()

async def list_chains(db: AsyncSession) -> List[Chain]:
    result = await db.execute(select(Chain))
    return result.scalars().all()

async def update_chain(db: AsyncSession, chain_db_id: int, **kwargs):
    chain = await db.get(Chain, chain_db_id)
    if not chain:
        return None
    for key, value in kwargs.items():
        if hasattr(chain, key):
            setattr(chain, key, value)
    await db.commit()
    await db.refresh(chain)
    return chain

async def delete_chain(db: AsyncSession, chain_db_id: int) -> bool:
    chain = await db.get(Chain, chain_db_id)
    if not chain:
        return False
    await db.delete(chain)
    await db.commit()
    return True

# Token registry
async def add_token(db: AsyncSession, **kwargs) -> ChainToken:
    token = ChainToken(**kwargs)
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return token

async def list_tokens(db: AsyncSession, chain_db_id: int) -> List[ChainToken]:
    result = await db.execute(select(ChainToken).where(ChainToken.chain_id == chain_db_id))
    return result.scalars().all()

async def get_token_by_symbol(db: AsyncSession, chain_db_id: int, symbol: str) -> Optional[ChainToken]:
    result = await db.execute(
        select(ChainToken)
        .where(ChainToken.chain_id == chain_db_id)
        .where(ChainToken.symbol == symbol)
    )
    return result.scalar_one_or_none()
