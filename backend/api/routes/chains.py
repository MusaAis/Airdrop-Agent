from fastapi import APIRouter, Depends, HTTPException, status
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import Chain, ChainToken
from backend.chains.manager import (
    create_chain, get_chain, get_chain_by_chain_id, list_chains,
    update_chain, delete_chain, add_token, list_tokens, get_token_by_symbol
)
from backend.chains.rpc_checker import check_all_rpcs
from pydantic import BaseModel, Field
from typing import List, Optional

router = APIRouter(prefix="/chains", tags=["chains"])

class ChainCreate(BaseModel):
    name: str
    chain_id: int
    rpc_urls: List[str]
    explorer_url: Optional[str] = None
    gas_token_symbol: str = "ETH"
    gas_token_is_native: bool = True
    gas_token_contract: Optional[str] = None
    gas_token_decimals: int = 18
    min_gas_balance_warning: float = 0.005
    min_gas_balance_critical: float = 0.001
    rpc_rate_limit_per_sec: int = 10
    enabled: bool = True

class ChainUpdate(BaseModel):
    name: Optional[str] = None
    rpc_urls: Optional[List[str]] = None
    explorer_url: Optional[str] = None
    gas_token_symbol: Optional[str] = None
    gas_token_is_native: Optional[bool] = None
    gas_token_contract: Optional[str] = None
    gas_token_decimals: Optional[int] = None
    min_gas_balance_warning: Optional[float] = None
    min_gas_balance_critical: Optional[float] = None
    rpc_rate_limit_per_sec: Optional[int] = None
    enabled: Optional[bool] = None

class TokenCreate(BaseModel):
    chain_id: int
    symbol: str
    contract_address: str
    decimals: int
    coingecko_id: Optional[str] = None
    is_gas_token: bool = False
    is_stable: bool = False

@router.get("/")
async def list_all_chains(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    chains = await list_chains(db)
    return chains

@router.post("/")
async def add_chain(data: ChainCreate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    existing = await get_chain_by_chain_id(db, data.chain_id)
    if existing:
        raise HTTPException(status_code=400, detail="Chain with this chain_id already exists")
    chain = await create_chain(db, **data.model_dump())
    return chain

@router.get("/{chain_db_id}")
async def get_chain_detail(chain_db_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    chain = await get_chain(db, chain_db_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return chain

@router.put("/{chain_db_id}")
async def update_chain_route(chain_db_id: int, data: ChainUpdate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    chain = await update_chain(db, chain_db_id, **data.model_dump(exclude_unset=True))
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return chain

@router.delete("/{chain_db_id}")
async def delete_chain_route(chain_db_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    success = await delete_chain(db, chain_db_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chain not found")
    return {"message": "Deleted"}

@router.post("/{chain_db_id}/test-rpc")
async def test_chain_rpc(chain_db_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    chain = await get_chain(db, chain_db_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    results = await check_all_rpcs(chain)
    return results

# Token endpoints
@router.get("/{chain_db_id}/tokens")
async def list_chain_tokens(chain_db_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    tokens = await list_tokens(db, chain_db_id)
    return tokens

@router.post("/{chain_db_id}/tokens")
async def add_chain_token(chain_db_id: int, data: TokenCreate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    # verify chain exists
    chain = await get_chain(db, chain_db_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    token = await add_token(db, **data.model_dump(exclude={'chain_id'}), chain_id=chain_db_id)
    return token
