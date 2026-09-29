"""
Token registry — resolves symbol → (contract_address, decimals) per chain.
Acts as a cache layer over the chain_tokens DB table.
"""
import logging
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import ChainToken, Chain

logger = logging.getLogger("airdrop.token_registry")

# In-memory cache: (chain_db_id, symbol.upper()) -> (contract_address, decimals)
_cache: dict[tuple, Tuple[Optional[str], int]] = {}


async def resolve_token(
    db: AsyncSession,
    chain_db_id: int,
    symbol: str,
) -> Tuple[Optional[str], int]:
    """
    Resolve token symbol to (contract_address, decimals).
    Returns (None, 18) for native tokens.
    Raises ValueError if token not found.
    """
    key = (chain_db_id, symbol.upper())
    if key in _cache:
        return _cache[key]

    result = await db.execute(
        select(ChainToken).where(
            ChainToken.chain_id == chain_db_id,
            ChainToken.symbol == symbol.upper(),
        )
    )
    token = result.scalar_one_or_none()

    if not token:
        raise ValueError(
            f"Token '{symbol}' not registered on chain_db_id={chain_db_id}. "
            f"Add it via dashboard or chain.add_token Telegram command."
        )

    entry = (token.contract_address, token.decimals)
    _cache[key] = entry
    return entry


async def get_token_decimals(
    db: AsyncSession, chain_db_id: int, symbol: str
) -> int:
    _, decimals = await resolve_token(db, chain_db_id, symbol)
    return decimals


async def get_token_contract(
    db: AsyncSession, chain_db_id: int, symbol: str
) -> Optional[str]:
    contract, _ = await resolve_token(db, chain_db_id, symbol)
    return contract


async def get_token_address(
    chain_db_id: int, symbol: str, db: AsyncSession
) -> Optional[str]:
    """Phase 5 fix: tasks/swap.py imports this (argument order chain, symbol,
    db) but it did not exist, so every swap using a token symbol failed."""
    contract, _ = await resolve_token(db, chain_db_id, symbol)
    return contract


async def get_wrapped_native(chain_db_id: int, db: AsyncSession) -> Optional[str]:
    """Phase 5 fix (same import gap as above). Looks for a registered token
    named 'W' + the chain's gas symbol (WETH, WBNB, ...). Returns None if not
    registered; swap.py then falls back to task_config.parameters
    ['wrapped_native_address']."""
    chain = await db.get(Chain, chain_db_id)
    if not chain:
        return None
    try:
        contract, _ = await resolve_token(db, chain_db_id, f"W{chain.gas_token_symbol}")
        return contract
    except ValueError:
        return None


async def register_token(
    db: AsyncSession,
    chain_db_id: int,
    symbol: str,
    contract_address: Optional[str],
    decimals: int,
    coingecko_id: Optional[str] = None,
    is_gas_token: bool = False,
    is_stable: bool = False,
) -> ChainToken:
    """Add or update a token in the registry."""
    result = await db.execute(
        select(ChainToken).where(
            ChainToken.chain_id == chain_db_id,
            ChainToken.symbol == symbol.upper(),
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.contract_address = contract_address
        existing.decimals = decimals
        if coingecko_id:
            existing.coingecko_id = coingecko_id
        await db.commit()
        token = existing
    else:
        token = ChainToken(
            chain_id=chain_db_id,
            symbol=symbol.upper(),
            contract_address=contract_address,
            decimals=decimals,
            coingecko_id=coingecko_id,
            is_gas_token=is_gas_token,
            is_stable=is_stable,
        )
        db.add(token)
        await db.commit()
        await db.refresh(token)

    # Invalidate cache
    _cache.pop((chain_db_id, symbol.upper()), None)
    logger.info(f"Token registered: {symbol} on chain {chain_db_id} @ {contract_address}")
    return token


async def list_tokens(db: AsyncSession, chain_db_id: int) -> list:
    result = await db.execute(
        select(ChainToken).where(ChainToken.chain_id == chain_db_id)
    )
    tokens = result.scalars().all()
    return [
        {
            "symbol": t.symbol,
            "contract_address": t.contract_address,
            "decimals": t.decimals,
            "coingecko_id": t.coingecko_id,
            "is_gas_token": t.is_gas_token,
            "is_stable": t.is_stable,
        }
        for t in tokens
    ]


def clear_cache():
    """Force-clear the in-memory cache (call after bulk token updates)."""
    _cache.clear()
