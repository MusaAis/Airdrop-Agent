from fastapi import APIRouter, Depends, HTTPException
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import Faucet, FaucetToken, FaucetRequest, Wallet
from backend.faucet.manager import request_faucet_for_wallet
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone

router = APIRouter(prefix="/faucets", tags=["faucets"])


class FaucetTokenOut(BaseModel):
    id: int
    token_symbol: str
    token_contract: Optional[str] = None
    amount_given: float
    decimals: int

    model_config = {"from_attributes": True}


class FaucetOut(BaseModel):
    id: int
    chain_id: Optional[int] = None
    project_id: Optional[int] = None
    name: str
    url: str
    fallback_urls: Optional[list] = None
    method: str
    body_template: Optional[dict] = None
    cooldown_hours: int
    enabled: bool
    tokens: List[FaucetTokenOut] = []

    model_config = {"from_attributes": True}


class FaucetCreate(BaseModel):
    chain_id: Optional[int] = None
    project_id: Optional[int] = None
    name: str
    url: str
    fallback_urls: List[str] = []
    method: str = "POST"
    body_template: dict = {}
    cooldown_hours: int = 24
    enabled: bool = True
    # Tokens can be created inline at faucet-creation time, instead of a
    # separate POST /faucets/tokens call per token — convenience addition,
    # not in the original spec, but the dashboard create-faucet form needs
    # to be able to register e.g. "this faucet gives 0.1 ETH + 50 USDC" in
    # one step rather than three sequential requests.
    tokens: List[dict] = []


class FaucetTokenCreate(BaseModel):
    faucet_id: int
    token_symbol: str
    token_contract: Optional[str] = None
    amount_given: float
    decimals: int


class FaucetUpdate(BaseModel):
    chain_id: Optional[int] = None
    project_id: Optional[int] = None
    name: Optional[str] = None
    url: Optional[str] = None
    fallback_urls: Optional[List[str]] = None
    enabled: Optional[bool] = None
    cooldown_hours: Optional[int] = None
    method: Optional[str] = None
    body_template: Optional[dict] = None


async def _faucet_with_tokens(db: AsyncSession, faucet: Faucet) -> FaucetOut:
    tokens = (await db.execute(select(FaucetToken).where(FaucetToken.faucet_id == faucet.id))).scalars().all()
    return FaucetOut(
        id=faucet.id, chain_id=faucet.chain_id, project_id=faucet.project_id,
        name=faucet.name, url=faucet.url, fallback_urls=faucet.fallback_urls,
        method=faucet.method, body_template=faucet.body_template,
        cooldown_hours=faucet.cooldown_hours, enabled=faucet.enabled,
        tokens=[FaucetTokenOut.model_validate(t) for t in tokens],
    )


@router.get("/", response_model=List[FaucetOut])
async def list_faucets(_user: dict = Depends(verify_token), chain_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    """List all faucets, each with its configured tokens nested — previously
    the frontend had to make a separate call per faucet to discover what
    tokens it gives out, and there was no UI for it at all."""
    stmt = select(Faucet)
    if chain_id:
        stmt = stmt.where(Faucet.chain_id == chain_id)
    faucets = (await db.execute(stmt)).scalars().all()
    return [await _faucet_with_tokens(db, f) for f in faucets]


@router.get("/{faucet_id}", response_model=FaucetOut)
async def get_faucet(faucet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    faucet = await db.get(Faucet, faucet_id)
    if not faucet:
        raise HTTPException(status_code=404, detail="Faucet not found")
    return await _faucet_with_tokens(db, faucet)


@router.post("/", response_model=FaucetOut)
async def create_faucet(data: FaucetCreate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    payload = data.model_dump(exclude={"tokens"})
    faucet = Faucet(**payload)
    db.add(faucet)
    await db.commit()
    await db.refresh(faucet)
    for t in data.tokens:
        db.add(FaucetToken(faucet_id=faucet.id, **t))
    if data.tokens:
        await db.commit()
    return await _faucet_with_tokens(db, faucet)


@router.put("/{faucet_id}", response_model=FaucetOut)
async def update_faucet(faucet_id: int, data: FaucetUpdate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Enable/disable or update a faucet — called by the dashboard toggle and
    edit form. Now also accepts chain_id/project_id/fallback_urls, which the
    previous FaucetUpdate schema omitted (so those fields were silently
    impossible to change once a faucet was created)."""
    faucet = await db.get(Faucet, faucet_id)
    if not faucet:
        raise HTTPException(status_code=404, detail="Faucet not found")
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(faucet, field, value)
    await db.commit()
    await db.refresh(faucet)
    return await _faucet_with_tokens(db, faucet)


@router.delete("/{faucet_id}")
async def delete_faucet(faucet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    faucet = await db.get(Faucet, faucet_id)
    if not faucet:
        raise HTTPException(status_code=404, detail="Faucet not found")
    # Clean up child token rows first (no ON DELETE CASCADE defined on the FK).
    tokens = (await db.execute(select(FaucetToken).where(FaucetToken.faucet_id == faucet_id))).scalars().all()
    for t in tokens:
        await db.delete(t)
    await db.delete(faucet)
    await db.commit()
    return {"message": f"Faucet {faucet_id} deleted"}


@router.post("/tokens", response_model=FaucetTokenOut)
async def add_faucet_token(data: FaucetTokenCreate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    token = FaucetToken(**data.model_dump())
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return token


@router.delete("/tokens/{token_id}")
async def delete_faucet_token(token_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Previously there was no way to remove a token from a faucet's config
    once added, short of editing the DB directly."""
    token = await db.get(FaucetToken, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Faucet token not found")
    await db.delete(token)
    await db.commit()
    return {"message": f"Token {token_id} removed"}


@router.post("/request/{wallet_id}/{chain_id}")
async def manual_faucet_request(wallet_id: int, chain_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    from backend.wallet.manager import get_wallet
    from backend.chains.manager import get_chain
    wallet = await get_wallet(db, wallet_id)
    chain = await get_chain(db, chain_id)
    if not wallet or not chain:
        raise HTTPException(status_code=404, detail="Wallet or chain not found")
    result = await request_faucet_for_wallet(wallet, chain, db)
    return result


@router.post("/request-all/{wallet_id}")
async def manual_faucet_request_all_chains(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """
    Claim from every faucet across every enabled chain for one wallet in a
    single call. The master plan's faucet spec says "request ALL tokens
    available per faucet (gas token AND any other tokens offered)" — this is
    the per-wallet, all-chains version of that: a single "claim everything
    this wallet is eligible for right now" button, instead of having to call
    /request/{wallet_id}/{chain_id} once per chain manually.
    """
    from backend.wallet.manager import get_wallet
    from backend.models import Chain
    wallet = await get_wallet(db, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    chains = (await db.execute(select(Chain).where(Chain.enabled == True))).scalars().all()
    results = {}
    for chain in chains:
        results[chain.name] = await request_faucet_for_wallet(wallet, chain, db)
    return results


class FaucetStatusOut(BaseModel):
    faucet_id: int
    faucet_name: str
    chain_id: Optional[int] = None
    claimable_now: bool
    cooldown_remaining_hours: Optional[float] = None
    last_requested_at: Optional[str] = None
    last_status: Optional[str] = None


@router.get("/status/{wallet_id}", response_model=List[FaucetStatusOut])
async def faucet_status_for_wallet(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """
    Per-faucet cooldown status for a wallet — claimable now vs. how long
    until it is. Backs the Faucets page's per-wallet status view, and is
    what the Telegram faucet.status command should also read from (see
    telegram/commands/faucet.py). Previously there was no route exposing
    this — cooldown logic only lived inside request_faucet_for_wallet,
    invisible until you actually tried to claim and got told "on cooldown".
    """
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    faucets = (await db.execute(select(Faucet).where(Faucet.enabled == True))).scalars().all()
    out = []
    for faucet in faucets:
        last_req = (await db.execute(
            select(FaucetRequest)
            .where(FaucetRequest.wallet_id == wallet_id, FaucetRequest.faucet_id == faucet.id)
            .order_by(FaucetRequest.requested_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        claimable = True
        remaining = None
        last_at = None
        last_status = None
        if last_req:
            req_at = last_req.requested_at
            if req_at.tzinfo is None:
                req_at = req_at.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - req_at).total_seconds() / 3600
            last_at = req_at.isoformat()
            last_status = last_req.status
            if hours_since < faucet.cooldown_hours:
                claimable = False
                remaining = round(faucet.cooldown_hours - hours_since, 1)

        out.append(FaucetStatusOut(
            faucet_id=faucet.id, faucet_name=faucet.name, chain_id=faucet.chain_id,
            claimable_now=claimable, cooldown_remaining_hours=remaining,
            last_requested_at=last_at, last_status=last_status,
        ))
    return out
