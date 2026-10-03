from fastapi import APIRouter, Depends, HTTPException, status
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import AgentStatus
from backend.agent import start_agent, stop_agent, worker_pool
from backend.config import MASTER_PASSWORD
from backend.core.kill_switch import is_emergency_stop, is_dry_run
from pydantic import BaseModel

router = APIRouter(prefix="/agent", tags=["agent"])

@router.get("/health")
async def health_check():
    return {"status": "alive", "emergency_stop": is_emergency_stop()}

@router.get("/status")
async def agent_status(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    status_record = await db.get(AgentStatus, 1)
    if not status_record:
        return {"status": "stopped", "message": "No status record"}
    return {
        "status": status_record.status,
        "uptime_start": status_record.uptime_start,
        "last_heartbeat": status_record.last_heartbeat,
        "memory_pct": status_record.memory_pct,
        "worker_slots_active": status_record.worker_slots_active,
        "worker_slots_max": status_record.worker_slots_max,
        "emergency_stop": is_emergency_stop(),
        "dry_run": is_dry_run(),
        "current_tasks": status_record.current_tasks
    }

@router.post("/start")
async def agent_start(_user: dict = Depends(verify_token)):
    if is_emergency_stop():
        raise HTTPException(400, "Cannot start while emergency stop active")
    start_agent()
    return {"message": "Agent start initiated"}

@router.post("/stop")
async def agent_stop(_user: dict = Depends(verify_token)):
    stop_agent()
    return {"message": "Agent stop initiated"}

@router.post("/kill")
async def agent_kill(
    reason: str = "manual",
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(verify_token),
):
    from backend.core.kill_switch import activate_kill_switch
    queued_count = len(worker_pool.queue)
    async with worker_pool.lock:
        worker_pool.queue.clear()
        worker_pool.active_task_ids.clear()
    await activate_kill_switch(db, reason=reason)
    stop_agent()
    return {
        "message": "Emergency stop activated",
        "reason": reason,
        "cleared_queue_items": queued_count,
    }

@router.get("/workers")
async def worker_slots(_user: dict = Depends(verify_token)):
    slots_info = []
    for i, s in enumerate(worker_pool.slots):
        if s:
            slots_info.append({
                "slot": i,
                "wallet_id": s["wallet"].id if s else None,
                "project": s["project"].name if s else None,
                "task_type": s["task_config"].task_type if s else None,
                "chain_id": s["chain"].id if s else None
            })
        else:
            slots_info.append({"slot": i, "status": "idle"})
    return slots_info

@router.get("/queue")
async def queue_preview(_user: dict = Depends(verify_token)):
    return [{"wallet_id": q["wallet"].id, "task_type": q["task_config"].task_type, "priority": q["priority"]} for q in worker_pool.queue]

from backend.wallet.hd_generator import set_master_seed, encrypt_seed, decrypt_seed, get_master_seed, derive_hd_wallet
from backend.database import async_session
from backend.models import AgentSecret
from sqlalchemy import select
import logging

logger = logging.getLogger("airdrop.agent.seed")

class SetSeedRequest(BaseModel):
    mnemonic: str

class UnlockRequest(BaseModel):
    master_password: str

@router.post("/set-seed")
async def set_seed(
    req: SetSeedRequest,
    _user: dict = Depends(verify_token)
):
    """Encrypt and store the master seed mnemonic."""
    encrypted = encrypt_seed(req.mnemonic, MASTER_PASSWORD)
    async with async_session() as db:
        # upsert
        existing = (await db.execute(select(AgentSecret).where(AgentSecret.key == 'master_mnemonic'))).scalar_one_or_none()
        if existing:
            existing.value = encrypted
        else:
            db.add(AgentSecret(key='master_mnemonic', value=encrypted))
        await db.commit()
    # Also set in current memory
    set_master_seed(req.mnemonic)
    return {"status": "seed stored securely"}

@router.post("/unlock")
async def unlock_seed(
    req: UnlockRequest,
    _user: dict = Depends(verify_token)
):
    """Decrypt stored seed and load into memory."""
    async with async_session() as db:
        entry = (await db.execute(select(AgentSecret).where(AgentSecret.key == 'master_mnemonic'))).scalar_one_or_none()
        if not entry:
            raise HTTPException(status_code=404, detail="No stored seed. Use set-seed first.")
    try:
        mnemonic = decrypt_seed(entry.value, req.master_password)
        set_master_seed(mnemonic)
        return {"status": "seed unlocked and active"}
    except Exception:
        raise HTTPException(status_code=400, detail="Wrong master password or corrupted seed")

# H6: the former POST /agent/wallets/{id}/private-key endpoint was removed. It returned a raw
# private key to anyone holding a login token plus MASTER_PASSWORD, which is the same value as
# the login password, so one stolen credential exposed every HD wallet. HD keys can be derived
# offline from your recovery phrase (path m/44'/60'/0'/0/{hd_index}); nothing in the dashboard
# or Telegram bot used this route.

from backend.models import Alert as AlertModel
from sqlalchemy import select as _sel

@router.get("/alerts-list")
async def list_alerts_compat(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(_sel(AlertModel).order_by(AlertModel.created_at.desc()).limit(50))).scalars().all()
    return [{"id": r.id, "type": r.type, "severity": r.severity, "message": r.message, "wallet_id": r.wallet_id, "project_id": r.project_id, "resolved": r.resolved, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    alert = await db.get(AlertModel, alert_id)
    if not alert: raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = True; await db.commit()
    return {"ok": True}

@router.post("/alerts/resolve-all")
async def resolve_all_alerts(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import update
    await db.execute(update(AlertModel).where(AlertModel.resolved == False).values(resolved=True))
    await db.commit()
    return {"ok": True}

@router.get("/alerts/snooze")
async def alert_snooze_status(_user: dict = Depends(verify_token)):
    from backend.telegram.commands.alert import snooze_until
    until = snooze_until()
    return {"snoozed": until is not None, "until": until.isoformat() if until else None}

@router.post("/alerts/snooze")
async def alert_snooze_set(minutes: int = 30, _user: dict = Depends(verify_token)):
    from backend.telegram.commands.alert import set_snooze
    minutes = max(1, min(1440, minutes))
    until = set_snooze(minutes)
    return {"snoozed": True, "until": until.isoformat()}

@router.delete("/alerts/snooze")
async def alert_snooze_clear(_user: dict = Depends(verify_token)):
    from backend.telegram.commands.alert import clear_snooze
    clear_snooze()
    return {"snoozed": False, "until": None}
