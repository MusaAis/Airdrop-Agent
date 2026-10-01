"""
Control-panel endpoints for everything that moved off Telegram (PLAN.md §4, Phase 7).
All under /ops so they cannot collide with the /projects/{project_id} style routes.
"""
import random
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.security.auth import verify_token
from backend.models import Wallet, WalletNonce
from backend.projects.manager import (
    get_project, update_project, get_task_config, update_task_config, list_task_configs,
)
from backend.projects.criteria import (
    list_criteria, add_criterion, update_criterion, delete_criterion,
)
from backend.projects.circuit_breaker import reset_circuit
from backend.wallet.manager import get_wallet
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
    else:
        rows = (await db.execute(
            select(Wallet).where(Wallet.status == "active", Wallet.is_gas_wallet == False)
        )).scalars().all()
        if not rows:
            raise HTTPException(400, "No active wallets")
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
    return {**_system_state(), "message": "Emergency stop cleared. Start the agent if it is stopped."}


@router.post("/system/archive-logs")
async def system_archive_logs(_user: dict = Depends(verify_token)):
    from backend.maintenance.log_archiver import run_all_maintenance
    return await run_all_maintenance()
