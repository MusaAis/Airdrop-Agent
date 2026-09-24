"""
WebSocket endpoint for real-time dashboard updates.
Streams: new log entries, agent status, worker slot assignments.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import async_session, get_db
from backend.models import Log, AgentStatus
from backend.security.auth import verify_token_str, verify_token

router = APIRouter()
logger = logging.getLogger("airdrop.ws")

# Connection manager — tracks all active WebSocket clients
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.debug(f"WS connected, total={len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.debug(f"WS disconnected, total={len(self.active)}")

    async def broadcast(self, message: dict):
        payload = json.dumps(message, default=str)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


def get_manager() -> ConnectionManager:
    return manager


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, token: str = Query(default=None)):
    """
    Real-time log stream.
    Client connects with ?token=<jwt>
    Receives JSON events: {type: "log"|"status"|"heartbeat", data: {...}}
    """
    # Auth check
    if token:
        try:
            verify_token_str(token)
        except Exception:
            await websocket.close(code=4001)
            return
    else:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket)

    # Send initial agent status on connect
    try:
        async with async_session() as db:
            status = await db.get(AgentStatus, 1)
            if status:
                await websocket.send_text(json.dumps({
                    "type": "status",
                    "data": {
                        "status": status.status,
                        "last_heartbeat": str(status.last_heartbeat),
                        "worker_slots_active": status.worker_slots_active,
                        "worker_slots_max": status.worker_slots_max,
                        "memory_pct": status.memory_pct,
                        "current_tasks": status.current_tasks or [],
                    }
                }, default=str))
    except Exception as e:
        logger.error(f"WS initial status error: {e}")

    last_log_id = 0

    # Poll for new logs and push to client
    try:
        while True:
            try:
                async with async_session() as db:
                    # Get new logs since last push
                    result = await db.execute(
                        select(Log)
                        .where(Log.id > last_log_id)
                        .order_by(Log.id.asc())
                        .limit(20)
                    )
                    new_logs = result.scalars().all()

                    for log in new_logs:
                        await websocket.send_text(json.dumps({
                            "type": "log",
                            "data": {
                                "id": log.id,
                                "wallet_id": log.wallet_id,
                                "chain_id": log.chain_id,
                                "task_name": log.task_name,
                                "tx_hash": log.tx_hash,
                                "status": log.status,
                                "error_message": log.error_message,
                                "gas_used": log.gas_used,
                                "gas_cost_usd": log.gas_cost_usd,
                                "is_dry_run": log.is_dry_run,
                                "created_at": str(log.created_at),
                            }
                        }, default=str))
                        last_log_id = log.id

                    # Push agent heartbeat
                    status = await db.get(AgentStatus, 1)
                    if status:
                        await websocket.send_text(json.dumps({
                            "type": "heartbeat",
                            "data": {
                                "last_heartbeat": str(status.last_heartbeat),
                                "worker_slots_active": status.worker_slots_active,
                                "memory_pct": status.memory_pct,
                                "current_tasks": status.current_tasks or [],
                                "ts": str(datetime.now(timezone.utc)),
                            }
                        }, default=str))

            except Exception as e:
                logger.error(f"WS poll error: {e}")

            await asyncio.sleep(2)  # poll every 2 seconds

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WS error: {e}")
        manager.disconnect(websocket)


@router.get("/ws/recent-logs")
async def recent_logs_http(limit: int = 50, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """HTTP polling fallback for live log — works through Cloudflare Tunnel."""
    from sqlalchemy import select as _sel
    from backend.models import Log
    rows = (await db.execute(
        _sel(Log).order_by(Log.created_at.desc()).limit(limit)
    )).scalars().all()
    return [
        {"id": r.id, "wallet_id": r.wallet_id, "task_name": r.task_name,
         "status": r.status, "tx_hash": r.tx_hash, "error_message": r.error_message,
         "gas_cost_usd": r.gas_cost_usd, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in reversed(rows)
    ]
