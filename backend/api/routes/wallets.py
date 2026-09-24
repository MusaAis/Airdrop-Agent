from fastapi import APIRouter, Depends, HTTPException, status
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import Wallet
from backend.wallet.manager import (
    create_hd_wallets, import_private_key, list_wallets, get_wallet,
    update_wallet_status, archive_wallet, pause_wallet, resume_wallet,
    blacklist_wallet, set_gas_wallet_flag, get_wallet_settings, update_wallet_settings
)
from backend.wallet.persona import assign_default_persona
from pydantic import BaseModel, Field
from typing import List, Optional

router = APIRouter(prefix="/wallets", tags=["wallets"])

class WalletCreateHD(BaseModel):
    count: int = 1
    start_index: int = 0
    tags: List[str] = []

class WalletImport(BaseModel):
    private_key: str
    name: Optional[str] = None
    tags: List[str] = []

class WalletSettingsUpdate(BaseModel):
    amount_min_override: Optional[float] = None
    amount_max_override: Optional[float] = None
    amount_distribution: Optional[str] = None
    amount_vary_daily: Optional[bool] = None
    active_hour_start: Optional[int] = None
    active_hour_end: Optional[int] = None
    start_offset_max_mins: Optional[int] = None
    sleep_min_mins: Optional[int] = None
    sleep_max_mins: Optional[int] = None
    gas_multiplier: Optional[float] = None
    bidirectional_default: Optional[bool] = None
    daily_tx_min: Optional[int] = None
    daily_tx_max: Optional[int] = None


class WalletResponse(BaseModel):
    id: int
    address: str
    hd_index: Optional[int] = None
    is_hd: bool = False
    status: str
    is_gas_wallet: bool = False
    tags: Optional[list] = None
    persona: Optional[dict] = None
    failure_count: int = 0

    model_config = {"from_attributes": True}

@router.get("/", response_model=list[WalletResponse])
async def list_all_wallets(_user: dict = Depends(verify_token), status: Optional[str] = None, tag: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    wallets = await list_wallets(db, status_filter=status, tag=tag)
    return wallets

class BalanceResponse(BaseModel):
    chain_id: int
    token_symbol: str
    balance: float
    usd_value: Optional[float] = None
    last_updated: Optional[str] = None

    model_config = {"from_attributes": True}


class WalletBalanceSummary(BaseModel):
    wallet_id: int
    address: str
    status: str
    is_gas_wallet: bool
    total_usd: float
    balances: List[BalanceResponse]


@router.get("/balances/all", response_model=List[WalletBalanceSummary])
async def get_all_wallet_balances(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """
    Bulk summary across every wallet — backs the Balances tab's main table
    (which wallets have funds, which are empty, total USD per wallet).
    Reads stored data only; does not hit any RPC. Use the per-wallet refresh
    route, or POST /wallets/balances/refresh-all, to update stale data.
    """
    from sqlalchemy import select
    from backend.models import WalletBalance
    wallets = await list_wallets(db)
    all_balances = (await db.execute(select(WalletBalance))).scalars().all()
    by_wallet = {}
    for b in all_balances:
        by_wallet.setdefault(b.wallet_id, []).append(b)

    out = []
    for w in wallets:
        rows = by_wallet.get(w.id, [])
        total_usd = sum((r.usd_value or 0.0) for r in rows)
        out.append(WalletBalanceSummary(
            wallet_id=w.id, address=w.address, status=w.status, is_gas_wallet=w.is_gas_wallet,
            total_usd=total_usd,
            balances=[
                BalanceResponse(
                    chain_id=r.chain_id, token_symbol=r.token_symbol, balance=r.balance,
                    usd_value=r.usd_value, last_updated=r.last_updated.isoformat() if r.last_updated else None,
                )
                for r in rows
            ],
        ))
    return out


@router.post("/balances/refresh-all")
async def refresh_all_wallet_balances_route(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """
    Refresh live on-chain balances for every active wallet across every
    enabled chain. This can be slow (N wallets x M chains x tokens, each an
    RPC call) — runs sequentially and returns a count when done. For a large
    wallet set, prefer refreshing individual wallets from the UI, or wire
    this into the existing 6-hour scheduler instead of calling it ad hoc.
    """
    from sqlalchemy import select
    from backend.models import Chain
    from backend.wallet.balance import refresh_wallet_balances
    wallets = await list_wallets(db, status_filter="active")
    chains = (await db.execute(select(Chain).where(Chain.enabled == True))).scalars().all()
    total_rows = 0
    for w in wallets:
        rows = await refresh_wallet_balances(db, w, chains)
        total_rows += len(rows)
    return {"message": f"Refreshed {len(wallets)} wallet(s) across {len(chains)} chain(s)", "balance_rows_updated": total_rows}

@router.get("/{wallet_id}", response_model=WalletResponse)
async def get_wallet_detail(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    wallet = await get_wallet(db, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet

@router.post("/generate")
async def generate_hd_wallets(data: WalletCreateHD, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    wallets = await create_hd_wallets(db, data.count, data.start_index, data.tags)
    # assign default persona and settings (settings already created)
    for w in wallets:
        persona = assign_default_persona()
        w.persona = persona
        # update settings with persona values
        settings = await get_wallet_settings(db, w.id)
        await update_wallet_settings(db, w.id, **persona)
    await db.commit()
    return [{"address": w.address, "id": w.id, "hd_index": w.hd_index} for w in wallets]

@router.post("/import")
async def import_wallet(data: WalletImport, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    from backend.config import MASTER_PASSWORD
    wallet = await import_private_key(db, data.private_key, MASTER_PASSWORD, data.name, data.tags)
    return {"address": wallet.address, "id": wallet.id}

@router.put("/{wallet_id}/status")
async def update_wallet_status_route(wallet_id: int, status: str, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    valid_statuses = ["active", "paused", "archived", "blacklisted"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of {valid_statuses}")
    wallet = await update_wallet_status(db, wallet_id, status)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {"message": f"Wallet {wallet_id} set to {status}"}

@router.put("/{wallet_id}/settings")
async def update_wallet_settings_route(wallet_id: int, data: WalletSettingsUpdate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    settings = await update_wallet_settings(db, wallet_id, **data.model_dump(exclude_unset=True))
    if not settings:
        raise HTTPException(status_code=404, detail="Wallet settings not found")
    return settings

@router.get("/{wallet_id}/settings")
async def get_wallet_settings_route(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    settings = await get_wallet_settings(db, wallet_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Wallet settings not found")
    return settings

@router.put("/{wallet_id}/gas-wallet")
async def set_gas_wallet_route(wallet_id: int, _user: dict = Depends(verify_token), is_gas: bool = True, db: AsyncSession = Depends(get_db)):
    await set_gas_wallet_flag(db, wallet_id, is_gas)
    return {"message": "Gas wallet flag updated"}




@router.get("/{wallet_id}/balances", response_model=List[BalanceResponse])
async def get_wallet_balances(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """
    Read the last-known balances for a wallet across all chains, from the
    wallet_balances table. Previously this table existed in the schema with
    no route exposing it and nothing populating it — there was no way to see
    fund status without checking a chain explorer manually per wallet.
    Returns whatever was last refreshed; call the /refresh endpoint below (or
    the bulk refresh) to update it with live on-chain data.
    """
    from sqlalchemy import select
    from backend.models import WalletBalance
    wallet = await get_wallet(db, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    result = await db.execute(select(WalletBalance).where(WalletBalance.wallet_id == wallet_id))
    rows = result.scalars().all()
    return [
        BalanceResponse(
            chain_id=r.chain_id, token_symbol=r.token_symbol, balance=r.balance,
            usd_value=r.usd_value, last_updated=r.last_updated.isoformat() if r.last_updated else None,
        )
        for r in rows
    ]


@router.post("/{wallet_id}/balances/refresh", response_model=List[BalanceResponse])
async def refresh_wallet_balances_route(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Live on-chain refresh for one wallet across every enabled chain."""
    from sqlalchemy import select
    from backend.models import Chain
    from backend.wallet.balance import refresh_wallet_balances
    wallet = await get_wallet(db, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    chains = (await db.execute(select(Chain).where(Chain.enabled == True))).scalars().all()
    rows = await refresh_wallet_balances(db, wallet, chains)
    return [
        BalanceResponse(
            chain_id=r.chain_id, token_symbol=r.token_symbol, balance=r.balance,
            usd_value=r.usd_value, last_updated=r.last_updated.isoformat() if r.last_updated else None,
        )
        for r in rows
    ]


