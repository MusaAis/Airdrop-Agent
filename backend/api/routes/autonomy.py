from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.security.auth import verify_token
from backend.core.autonomy import (
    autonomy_summary, list_actions, approve_action, undo_action, set_autonomy_paused,
)

router = APIRouter(prefix="/autonomy", tags=["autonomy"])


@router.get("/status")
async def autonomy_status(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    return await autonomy_summary(db)


@router.post("/pause")
async def autonomy_pause(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Freeze all AI autonomy. Same flag the Telegram /ai_autonomy_off uses; persisted."""
    await set_autonomy_paused(db, True, "dashboard")
    return await autonomy_summary(db)


@router.post("/resume")
async def autonomy_resume(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    await set_autonomy_paused(db, False, "dashboard")
    return await autonomy_summary(db)


@router.get("/actions")
async def autonomy_actions(
    limit: int = 50,
    status: Optional[str] = None,
    _user: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    return await list_actions(db, limit=max(1, min(200, limit)), status=status)


@router.post("/actions/{action_id}/approve")
async def autonomy_approve(action_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    ok, msg = await approve_action(db, action_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


@router.post("/actions/{action_id}/undo")
async def autonomy_undo(action_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Dismisses a suggestion, or reverts an applied action."""
    ok, msg = await undo_action(db, action_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}
