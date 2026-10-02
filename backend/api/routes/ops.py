"""
Control-panel endpoints for everything that moved off Telegram (PLAN.md §4, Phase 7).
All under /ops so they cannot collide with the /projects/{project_id} style routes.
"""
import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from backend.database import get_db
from backend.security.auth import verify_token
from backend.models import (
    Wallet, WalletNonce, WalletSettings, Transaction, Chain, Project, TaskConfig,
    ProjectContract, AgentStatus, AgentSecret,
)
from backend.projects.manager import (
    get_project, update_project, get_task_config, update_task_config, list_task_configs,
)
from backend.projects.criteria import (
    list_criteria, add_criterion, update_criterion, delete_criterion,
)
from backend.projects.circuit_breaker import reset_circuit
from backend.projects.contracts import add_contract, list_contracts, delete_contract
from backend.wallet.manager import get_wallet, get_wallet_settings, update_wallet_settings
from backend.wallet.persona import assign_default_persona
from backend.wallet.hd_generator import get_master_seed
from backend.chains.manager import get_chain
from backend.core.nonce_manager import release_nonce, sync_nonce_from_chain
from backend.core.kill_switch import (
    is_emergency_stop, is_dry_run, set_dry_run, deactivate_kill_switch, is_ai_autonomy_paused,
)

router = APIRouter(prefix="/ops", tags=["ops"])


# ═══════════════════════════ projects ═══════════════════════════
class ProjectDetails(BaseModel):
    priority: Optional[int] = None
    max_concurrent_wallets: Optional[int] = None
    website: Optional[str] = None
    twitter: Optional[str] = None
    discord: Optional[str] = None
    notes: Optional[str] = None
    tge_date: Optional[str] = None       # yyyy-mm-dd, "" clears
    airdrop_date: Optional[str] = None   # yyyy-mm-dd, "" clears


@router.put("/projects/{project_id}/details")
async def edit_project_details(
    project_id: int, data: ProjectDetails,
    _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db),
):
    """Priority, wallet cap, links, notes and the snapshot dates the Snapshot
    Calendar reads (there was previously no way to set tge_date/airdrop_date)."""
    fields = data.model_dump(exclude_unset=True)
    if "priority" in fields and not (1 <= fields["priority"] <= 10):
        raise HTTPException(400, "priority must be between 1 and 10")
    if "max_concurrent_wallets" in fields and not (1 <= fields["max_concurrent_wallets"] <= 50):
        raise HTTPException(400, "max_concurrent_wallets must be between 1 and 50")
    for key in ("tge_date", "airdrop_date"):
        if key in fields:
            v = fields[key]
            try:
                fields[key] = date.fromisoformat(v) if v else None
            except ValueError:
                raise HTTPException(400, f"{key} must look like 2026-12-31")
    for key in ("website", "twitter", "discord", "notes"):
        if key in fields and fields[key] == "":
            fields[key] = None
    project = await update_project(db, project_id, **fields)
    if not project:
        raise HTTPException(404, "Project not found")
    return {"message": f"'{project.name}' updated"}


@router.post("/projects/{project_id}/reset-circuit")
async def reset_project_circuit(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    project = await get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    await reset_circuit(db, project)
    return {"message": f"Circuit breaker reset for '{project.name}'"}


def _crit(c) -> dict:
    return {
        "id": c.id, "project_id": c.project_id, "type": c.type, "description": c.description,
        "threshold": c.threshold, "unit": c.unit, "uncertain": c.uncertain,
        "ai_extracted": c.ai_extracted, "source_quote": c.source_quote,
    }


class CriterionIn(BaseModel):
    type: str = "other"
    description: str
    threshold: Optional[float] = None
    unit: Optional[str] = None
    uncertain: bool = False


class CriterionEdit(BaseModel):
    type: Optional[str] = None
    description: Optional[str] = None
    threshold: Optional[float] = None
    unit: Optional[str] = None
    uncertain: Optional[bool] = None


@router.get("/projects/{project_id}/criteria")
async def get_criteria(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    return [_crit(c) for c in await list_criteria(db, project_id)]


@router.post("/projects/{project_id}/criteria")
async def create_criterion(project_id: int, data: CriterionIn, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    if not await get_project(db, project_id):
        raise HTTPException(404, "Project not found")
    if not data.description.strip():
        raise HTTPException(400, "description is required")
    c = await add_criterion(
        db, project_id=project_id, type=data.type, description=data.description.strip(),
        threshold=data.threshold, unit=data.unit, uncertain=data.uncertain, ai_extracted=False,
    )
    return _crit(c)


@router.put("/criteria/{criterion_id}")
async def edit_criterion(criterion_id: int, data: CriterionEdit, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    # update_criterion skips None values, so a threshold cannot be cleared here — delete and re-add instead
    c = await update_criterion(db, criterion_id, **data.model_dump(exclude_unset=True))
    if not c:
        raise HTTPException(404, "Criterion not found")
    return _crit(c)


@router.delete("/criteria/{criterion_id}")
async def remove_criterion(criterion_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    if not await delete_criterion(db, criterion_id):
        raise HTTPException(404, "Criterion not found")
    return {"message": "Deleted"}


# ═══════════════════════════ tasks ═══════════════════════════
_DISTRIBUTIONS = {"weighted_low", "weighted_high", "uniform"}


class TaskEdit(BaseModel):
    enabled: Optional[bool] = None
    frequency_mins: Optional[int] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    amount_distribution: Optional[str] = None
    amount_vary_daily: Optional[bool] = None
    daily_tx_min: Optional[int] = None
    daily_tx_max: Optional[int] = None
    slippage_tolerance: Optional[float] = None
    deadline_mins: Optional[int] = None
    token_in: Optional[str] = None
    token_out: Optional[str] = None
    bidirectional: Optional[bool] = None
    token_in_reverse: Optional[str] = None
    token_out_reverse: Optional[str] = None
    dependency_task_ids: Optional[List[int]] = None
    parameters: Optional[Dict[str, Any]] = None


def _reaches(graph: Dict[int, List[int]], start: int, target: int) -> bool:
    stack, seen = list(graph.get(start, [])), set()
    while stack:
        n = stack.pop()
        if n == target:
            return True
        if n in seen:
            continue
        seen.add(n)
        stack.extend(graph.get(n, []))
    return False


@router.put("/tasks/{task_id}")
async def edit_task(task_id: int, data: TaskEdit, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    task = await get_task_config(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    f = data.model_dump(exclude_unset=True)

    mn, mx = f.get("min_amount", task.min_amount), f.get("max_amount", task.max_amount)
    if mn is not None and mx is not None and (mn <= 0 or mx < mn):
        raise HTTPException(400, "amounts must be > 0 and max >= min")
    dmin, dmax = f.get("daily_tx_min", task.daily_tx_min), f.get("daily_tx_max", task.daily_tx_max)
    if dmin is not None and dmax is not None and (dmin < 1 or dmax < dmin):
        raise HTTPException(400, "daily tx range must be >= 1 and max >= min")
    if "amount_distribution" in f and f["amount_distribution"] not in _DISTRIBUTIONS:
        raise HTTPException(400, f"amount_distribution must be one of {sorted(_DISTRIBUTIONS)}")
    if "frequency_mins" in f and f["frequency_mins"] < 1:
        raise HTTPException(400, "frequency_mins must be >= 1")
    if "slippage_tolerance" in f and not (0 < f["slippage_tolerance"] <= 0.5):
        raise HTTPException(400, "slippage_tolerance must be between 0 and 0.5")

    if f.get("dependency_task_ids") is not None:
        deps = sorted(set(int(d) for d in f["dependency_task_ids"]))
        tasks = await list_task_configs(db, task.project_id)
        siblings = {t.id for t in tasks}
        if task_id in deps:
            raise HTTPException(400, "a task cannot depend on itself")
        bad = [d for d in deps if d not in siblings]
        if bad:
            raise HTTPException(400, f"dependency ids {bad} are not tasks of this project")
        graph = {t.id: list(t.dependency_task_ids or []) for t in tasks}
        graph[task_id] = deps
        if _reaches(graph, task_id, task_id):
            raise HTTPException(400, "those dependencies would create a cycle")
        f["dependency_task_ids"] = deps

    for k in ("token_in", "token_out", "token_in_reverse", "token_out_reverse"):
        if k in f and f[k] is not None:
            f[k] = f[k].strip() or None
    await update_task_config(db, task_id, **f)
    return {"message": f"Task #{task_id} updated"}


class TriggerRequest(BaseModel):
    wallet_id: Optional[int] = None


@router.post("/tasks/{task_id}/trigger")
async def trigger_task(task_id: int, data: TriggerRequest, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Queue one run of a task now (same as Telegram /task_trigger)."""
    if is_emergency_stop():
        raise HTTPException(400, "Emergency stop is active")
    task = await get_task_config(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    project = await get_project(db, task.project_id)
    chain = await get_chain(db, task.chain_id)
    if not project or not chain:
        raise HTTPException(400, "Task's project or chain is missing")
    if data.wallet_id:
        wallet = await get_wallet(db, data.wallet_id)
        if not wallet or wallet.status != "active" or wallet.is_gas_wallet:
            raise HTTPException(400, "Wallet must exist, be active and not be a gas wallet")
        if wallet.is_hd and get_master_seed() is None:
            raise HTTPException(400, "Master seed is locked - unlock it in Settings > System first")
    else:
        rows = (await db.execute(
            select(Wallet).where(Wallet.status == "active", Wallet.is_gas_wallet == False)
        )).scalars().all()
        if get_master_seed() is None:
            rows = [w for w in rows if not w.is_hd]
        if not rows:
            raise HTTPException(400, "No usable active wallets (is the master seed locked?)")
        wallet = random.choice(rows)
    from backend.agent import worker_pool
    await worker_pool.enqueue([{
        "wallet": wallet, "task_config": task, "project": project, "chain": chain,
        "priority": project.priority,
    }])
    mode = "DRY RUN — will simulate only" if is_dry_run() else "live"
    extra = "" if worker_pool.running else " (agent is stopped; it runs once the agent starts)"
    return {"message": f"Queued task #{task_id} for wallet #{wallet.id} [{mode}]{extra}"}


# ═══════════════════════════ wallets ═══════════════════════════
class TagsUpdate(BaseModel):
    tags: List[str]


@router.put("/wallets/{wallet_id}/tags")
async def set_wallet_tags(wallet_id: int, data: TagsUpdate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    w = await get_wallet(db, wallet_id)
    if not w:
        raise HTTPException(404, "Wallet not found")
    tags = sorted({t.strip().lower()[:32] for t in data.tags if t.strip()})[:20]
    w.tags = tags
    await db.commit()
    return {"tags": tags}


@router.post("/wallets/{wallet_id}/recover")
async def recover_wallet(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Cooldown/paused -> active with failure_count reset. Cooldown wallets were
    never auto-recovered, and just activating one left failure_count at 3 so a
    single new failure put it straight back into cooldown."""
    w = await get_wallet(db, wallet_id)
    if not w:
        raise HTTPException(404, "Wallet not found")
    if w.status not in ("cooldown", "paused"):
        raise HTTPException(400, f"Wallet is '{w.status}'; only cooldown or paused wallets can be recovered")
    w.status = "active"
    w.failure_count = 0
    await db.commit()
    return {"message": f"Wallet #{wallet_id} is active again"}


@router.get("/wallets/{wallet_id}/nonces")
async def wallet_nonces(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WalletNonce).where(WalletNonce.wallet_id == wallet_id))).scalars().all()
    return [
        {"chain_id": r.chain_id, "nonce": r.nonce, "locked": r.locked,
         "locked_at": r.locked_at.isoformat() if r.locked_at else None}
        for r in rows
    ]


@router.post("/wallets/{wallet_id}/nonces/{chain_id}/release")
async def release_wallet_nonce(wallet_id: int, chain_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    await release_nonce(db, wallet_id, chain_id, increment=False)
    return {"message": "Nonce lock released"}


@router.post("/wallets/{wallet_id}/nonces/{chain_id}/sync")
async def sync_wallet_nonce(wallet_id: int, chain_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    wallet = await get_wallet(db, wallet_id)
    chain = await get_chain(db, chain_id)
    if not wallet or not chain:
        raise HTTPException(404, "Wallet or chain not found")
    try:
        from backend.chains.rpc_pool import get_web3
        w3 = await get_web3(chain)
        onchain = await w3.eth.get_transaction_count(wallet.address)
    except Exception as e:
        raise HTTPException(502, f"RPC unavailable: {e}")
    await sync_nonce_from_chain(db, wallet_id, chain_id, onchain)
    return {"message": f"Nonce synced to {onchain}"}


# ═══════════════════════════ chains ═══════════════════════════
@router.get("/chains/{chain_id}/gas")
async def chain_gas(chain_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    chain = await get_chain(db, chain_id)
    if not chain:
        raise HTTPException(404, "Chain not found")
    from backend.chains.rpc_pool import get_web3
    from backend.chains.gas import get_gas_spike_status, get_optimal_gas_windows
    try:
        w3 = await get_web3(chain)
        status = await get_gas_spike_status(chain.id, w3)
    except Exception as e:
        raise HTTPException(502, f"RPC unavailable: {e}")
    return {"status": status, "optimal_windows": await get_optimal_gas_windows(chain.id)}


# ═══════════════════════════ system ═══════════════════════════
class DryRunRequest(BaseModel):
    enabled: bool


def _system_state() -> dict:
    from backend.agent import worker_pool
    return {
        "dry_run": is_dry_run(),
        "emergency_stop": is_emergency_stop(),
        "ai_autonomy_paused": is_ai_autonomy_paused(),
        "agent_running": worker_pool.running,
        "seed_loaded": get_master_seed() is not None,
    }


@router.get("/system")
async def system_state(_user: dict = Depends(verify_token)):
    return _system_state()


@router.post("/system/dry-run")
async def system_dry_run(data: DryRunRequest, _user: dict = Depends(verify_token)):
    """Global dry-run toggle (replaces the old per-task dry-run command).
    In-memory, like the emergency stop: resets to OFF on restart (kill_switch does
    not read the DRY_RUN_MODE env value — see PLAN 'Known, not built')."""
    set_dry_run(data.enabled)
    return _system_state()


@router.post("/system/emergency/clear")
async def system_clear_emergency(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    await deactivate_kill_switch(db)
    from backend.agent import worker_pool
    if not worker_pool.running:
        # deactivate_kill_switch writes status="running" unconditionally
        st = await db.get(AgentStatus, 1)
        if st:
            st.status = "stopped"
            await db.commit()
    return {**_system_state(), "message": "Emergency stop cleared. Start the agent if it is stopped."}


@router.post("/system/archive-logs")
async def system_archive_logs(_user: dict = Depends(verify_token)):
    from backend.maintenance.log_archiver import run_all_maintenance
    return await run_all_maintenance()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)   # DB stores naive UTC


@router.post("/system/agent/start")
async def system_agent_start(_user: dict = Depends(verify_token)):
    """Guarded start (the plain /agent/start route has no already-running check,
    so a double click would spawn a second agent loop and double the worker slots)."""
    import backend.agent as agent_mod
    if is_emergency_stop():
        raise HTTPException(400, "Clear the emergency stop first")
    t = agent_mod.agent_task
    if agent_mod.worker_pool.running or (t is not None and not t.done()):
        raise HTTPException(400, "Agent is already running (or still shutting down)")
    agent_mod.start_agent()
    return {**_system_state(), "message": "Agent starting"}


@router.post("/system/agent/stop")
async def system_agent_stop(_user: dict = Depends(verify_token)):
    import backend.agent as agent_mod
    agent_mod.stop_agent()
    return {"message": "Stop requested - tasks already running finish first"}


class UnlockRequest(BaseModel):
    master_password: str


@router.post("/system/unlock")
async def system_unlock(data: UnlockRequest, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Load the stored master seed into memory (same as Telegram /agent_unlock).

    AES-CBC has no MAC, so a WRONG password can still "decrypt" to garbage without raising.
    The check therefore has to be done on the result, but it must not be stricter than what
    the rest of the system accepts: the seed is used as-is by derive_hd_wallet, and Telegram's
    unlock takes any decrypted text. An earlier version required a perfect BIP39 checksum,
    which rejected a correct password whenever the stored phrase had stray spacing or casing.
    Best proof is an existing HD wallet: if the candidate seed re-derives its address, the
    password is right.
    """
    from backend.wallet.hd_generator import decrypt_seed, derive_hd_wallet, set_master_seed
    entry = (await db.execute(select(AgentSecret).where(AgentSecret.key == "master_mnemonic"))).scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "No stored seed. Set one first with POST /agent/set-seed")
    try:
        mnemonic = decrypt_seed(entry.value, data.master_password)
    except Exception:
        raise HTTPException(400, "Wrong master password")

    words = mnemonic.split()
    looks_like_phrase = (
        len(words) in (12, 15, 18, 21, 24)
        and all(w.isascii() and w.isalpha() for w in words)
    )
    if not looks_like_phrase:
        raise HTTPException(400, "Wrong master password")

    hd = (await db.execute(
        select(Wallet).where(Wallet.is_hd == True, Wallet.hd_index.is_not(None)).order_by(Wallet.id).limit(1)
    )).scalar_one_or_none()
    if hd is not None:
        try:
            ok = derive_hd_wallet(hd.hd_index, mnemonic)["address"].lower() == (hd.address or "").lower()
        except Exception:
            ok = False
        if not ok:
            raise HTTPException(400, "Wrong master password (the decrypted seed does not match your existing wallets)")

    set_master_seed(mnemonic)
    return {**_system_state(), "message": "Seed unlocked"}


# ═══════════════════════ wallet settings (validated) ═══════════════════════
_DIST = {"weighted_low", "weighted_high", "uniform"}
_NULLABLE = {"amount_min_override", "amount_max_override", "active_hour_start", "active_hour_end"}
_DEFAULTS = {"start_offset_max_mins": 45, "sleep_min_mins": 2, "sleep_max_mins": 8,
             "gas_multiplier": 1.0, "daily_tx_min": 2, "daily_tx_max": 7}


class SettingsIn(BaseModel):
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


@router.put("/wallets/{wallet_id}/settings")
async def save_wallet_settings(wallet_id: int, data: SettingsIn, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Validated replacement for PUT /wallets/{id}/settings. That route let a blank
    field write NULL into NOT NULL columns (500) and accepted any value."""
    if not await get_wallet(db, wallet_id):
        raise HTTPException(404, "Wallet not found")
    cur = await get_wallet_settings(db, wallet_id)
    # explicit null only clears the nullable columns; required ones keep their value
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None or k in _NULLABLE}

    def val(k):
        v = fields[k] if k in fields else (getattr(cur, k, None) if cur else None)
        return _DEFAULTS.get(k) if v is None and k in _DEFAULTS else v

    a_min, a_max = val("amount_min_override"), val("amount_max_override")
    hs, he = val("active_hour_start"), val("active_hour_end")
    smin, smax = val("sleep_min_mins"), val("sleep_max_mins")
    dmin, dmax = val("daily_tx_min"), val("daily_tx_max")
    off, gas = val("start_offset_max_mins"), val("gas_multiplier")
    dist = val("amount_distribution")

    if (a_min is not None and a_min <= 0) or (a_max is not None and a_max <= 0):
        raise HTTPException(400, "amount overrides must be > 0")
    if a_min is not None and a_max is not None and a_max < a_min:
        raise HTTPException(400, "amount max override must be >= min override")
    if (hs is None) != (he is None):
        raise HTTPException(400, "set both active-hour fields, or leave both empty")
    if hs is not None and not (0 <= hs <= 23 and 0 <= he <= 23):
        raise HTTPException(400, "active hours must be 0-23 (UTC)")
    if not (1 <= smin <= smax <= 1440):
        raise HTTPException(400, "sleep must satisfy 1 <= min <= max <= 1440 minutes")
    if not (1 <= dmin <= dmax <= 50):
        raise HTTPException(400, "daily tx must satisfy 1 <= min <= max <= 50")
    if not (0 <= off <= 720):
        raise HTTPException(400, "start offset must be 0-720 minutes")
    if not (0.5 <= gas <= 3.0):
        raise HTTPException(400, "gas multiplier must be between 0.5 and 3.0")
    if dist is not None and dist not in _DIST:
        raise HTTPException(400, f"amount_distribution must be one of {sorted(_DIST)}")

    fields["updated_at"] = _now()
    await update_wallet_settings(db, wallet_id, **fields)
    return {"message": "Settings saved"}


async def _apply_persona(db: AsyncSession, w: Wallet) -> dict:
    """New random persona (same generator as wallet creation). Not committed."""
    persona = assign_default_persona()
    w.persona = persona
    ws = await get_wallet_settings(db, w.id)
    if ws is None:
        ws = WalletSettings(wallet_id=w.id)
        db.add(ws)
    for k, v in persona.items():
        if hasattr(ws, k):
            setattr(ws, k, v)
    ws.updated_at = _now()
    return persona


@router.post("/wallets/{wallet_id}/persona/reroll")
async def reroll_persona(wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    w = await get_wallet(db, wallet_id)
    if not w:
        raise HTTPException(404, "Wallet not found")
    await _apply_persona(db, w)
    await db.commit()
    return {"message": f"Wallet #{wallet_id} has a new random persona"}


@router.post("/persona/reroll-all")
async def reroll_all_personas(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """The website replacement for Telegram config_reset. Resetting every wallet to
    the SAME defaults would make them behave identically (a Sybil signal), so this
    gives each wallet its own fresh random persona instead."""
    rows = (await db.execute(
        select(Wallet).where(Wallet.is_gas_wallet == False, Wallet.status != "archived")
    )).scalars().all()
    for w in rows:
        await _apply_persona(db, w)
    await db.commit()
    return {"message": f"Re-rolled personas for {len(rows)} wallet(s)"}


# ═══════════════════════════ project contracts ═══════════════════════════
class ContractIn(BaseModel):
    chain_id: int            # internal chain DB id (same id the Chains page shows as "DB id")
    label: str
    address: str


def _contract(c: ProjectContract) -> dict:
    return {"id": c.id, "project_id": c.project_id, "chain_id": c.chain_id, "label": c.label, "address": c.address}


@router.get("/projects/{project_id}/contracts")
async def get_contracts(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    return [_contract(c) for c in await list_contracts(db, project_id)]


@router.post("/projects/{project_id}/contracts")
async def create_contract(project_id: int, data: ContractIn, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    if not await get_project(db, project_id):
        raise HTTPException(404, "Project not found")
    if not await get_chain(db, data.chain_id):
        raise HTTPException(400, "Chain not found")
    label = data.label.strip()
    if not label or len(label) > 60:
        raise HTTPException(400, "label is required (max 60 characters)")
    if not Web3.is_address(data.address.strip()):
        raise HTTPException(400, "address is not a valid EVM address (or its checksum is wrong)")
    addr = Web3.to_checksum_address(data.address.strip())
    dup = [c for c in await list_contracts(db, project_id) if c.chain_id == data.chain_id and c.address.lower() == addr.lower()]
    if dup:
        raise HTTPException(400, "That contract is already registered for this project on this chain")
    return _contract(await add_contract(db, project_id=project_id, chain_id=data.chain_id, label=label, address=addr))


@router.delete("/contracts/{contract_id}")
async def remove_contract(contract_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    if not await delete_contract(db, contract_id):
        raise HTTPException(404, "Contract not found")
    return {"message": "Deleted"}


# ═══════════════════════════ run all tasks of a project ═══════════════════════════
@router.post("/projects/{project_id}/trigger-all")
async def trigger_project_tasks(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Queue one run of every ENABLED task, each on a different wallet where possible
    (the queue drops a second item for the same wallet+chain, so picking wallets
    at random could silently lose tasks)."""
    if is_emergency_stop():
        raise HTTPException(400, "Emergency stop is active")
    project = await get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.status == "archived":
        raise HTTPException(400, "Project is archived")
    tasks = [t for t in await list_task_configs(db, project_id) if t.enabled]
    if not tasks:
        raise HTTPException(400, "No enabled tasks")
    wallets = (await db.execute(
        select(Wallet).where(Wallet.status == "active", Wallet.is_gas_wallet == False)
    )).scalars().all()
    if get_master_seed() is None:
        wallets = [w for w in wallets if not w.is_hd]
    if not wallets:
        raise HTTPException(400, "No usable active wallets (is the master seed locked?)")
    random.shuffle(wallets)
    used, items, skipped = set(), [], 0
    for t in tasks:
        chain = await get_chain(db, t.chain_id)
        if not chain or not chain.enabled:
            skipped += 1
            continue
        w = next((x for x in wallets if (x.id, chain.id) not in used), None)
        if w is None:
            skipped += 1
            continue
        used.add((w.id, chain.id))
        items.append({"wallet": w, "task_config": t, "project": project, "chain": chain, "priority": project.priority})
    if not items:
        raise HTTPException(400, "Nothing could be queued (disabled chains or not enough wallets)")
    from backend.agent import worker_pool
    await worker_pool.enqueue(items)
    mode = "DRY RUN - simulate only" if is_dry_run() else "live"
    note = f", {skipped} skipped (disabled chain / no free wallet)" if skipped else ""
    return {"message": f"Queued {len(items)} task(s) [{mode}]{note}"}


# ═══════════════════════════ transactions ═══════════════════════════
@router.get("/transactions")
async def list_transactions(
    status: Optional[str] = None, wallet_id: Optional[int] = None, project_id: Optional[int] = None,
    hours: int = Query(168, ge=1, le=24 * 90), limit: int = Query(100, ge=1, le=500),
    _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db),
):
    """On-chain transaction list with errors and explorer links (replaces the
    Telegram tx_status / tx_failed commands)."""
    stmt = (
        select(Transaction, Wallet.address, Chain.name, Chain.explorer_url, TaskConfig.task_type, Project.name)
        .join(Wallet, Transaction.wallet_id == Wallet.id)
        .join(Chain, Transaction.chain_id == Chain.id)
        .outerjoin(TaskConfig, Transaction.task_config_id == TaskConfig.id)
        .outerjoin(Project, TaskConfig.project_id == Project.id)
        .where(Transaction.created_at >= _now() - timedelta(hours=hours))
        .order_by(Transaction.id.desc()).limit(limit)
    )
    if status:
        stmt = stmt.where(Transaction.status == status)
    if wallet_id:
        stmt = stmt.where(Transaction.wallet_id == wallet_id)
    if project_id:
        stmt = stmt.where(TaskConfig.project_id == project_id)
    out = []
    for tx, addr, chain_name, explorer, task_type, proj_name in (await db.execute(stmt)).all():
        h = tx.tx_hash or ""
        if h and not h.startswith("0x"):
            h = "0x" + h
        out.append({
            "id": tx.id, "wallet_id": tx.wallet_id, "wallet": addr, "chain": chain_name,
            "project": proj_name, "task_type": task_type, "status": tx.status,
            "tx_hash": h, "explorer_url": f"{explorer.rstrip('/')}/tx/{h}" if explorer and h else None,
            "gas_used": tx.gas_used, "error": tx.error_message,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        })
    return out


# ═══════════════════════════ claims (scan only - claiming stays manual) ═══════════════════════════
@router.get("/claims/contracts")
async def claim_contracts(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Contracts the scanner will check: any project contract whose label contains 'claim'."""
    rows = (await db.execute(
        select(ProjectContract, Project.name, Chain.name)
        .join(Project, ProjectContract.project_id == Project.id)
        .join(Chain, ProjectContract.chain_id == Chain.id)
        .where(ProjectContract.label.ilike("%claim%"))
    )).all()
    return [{**_contract(c), "project": pn, "chain": cn} for c, pn, cn in rows]


@router.get("/claims/scan")
async def claims_scan(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    from backend.claims.manager import scan_claimable_airdrops
    try:
        return await asyncio.wait_for(scan_claimable_airdrops(db), timeout=150)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Scan took longer than 150s - try again or reduce the number of wallets/contracts")
