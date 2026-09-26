from fastapi import APIRouter, Depends, HTTPException
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import AIValidation
from backend.ai.orchestrator import dual_ai_validate
from backend.ai.prompts import prompt_risk, prompt_criteria, prompt_telegram_cmd, prompt_sybil, prompt_gap, prompt_config_validation
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/ai", tags=["ai"])

class AIRequest(BaseModel):
    task_type: str  # risk/criteria/telegram/sybil/gap/config
    input_data: str
    extra_data: Optional[str] = None

@router.post("/validate")
async def validate_with_ai(req: AIRequest, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    prompt_map = {
        "risk": prompt_risk,
        "criteria": prompt_criteria,
        "telegram": prompt_telegram_cmd,
        "sybil": prompt_sybil,
        "gap": prompt_gap,
        "config": prompt_config_validation,
    }
    if req.task_type not in prompt_map:
        raise HTTPException(400, f"Unknown task type. Choose from {list(prompt_map.keys())}")
    if req.task_type in ["gap", "config", "criteria"] and not req.extra_data:
        raise HTTPException(400, "extra_data required for this task type")
    user_prompt = prompt_map[req.task_type](req.input_data) if req.task_type in ["risk", "telegram", "sybil"] else prompt_map[req.task_type](req.input_data, req.extra_data)
    system_prompt = "You are a helpful assistant."
    validation = await dual_ai_validate(req.task_type, system_prompt, user_prompt, db)
    return {
        "id": validation.id,
        "agreement_score": validation.agreement_score,
        "requires_human": validation.requires_human,
        "conflicts": validation.conflict_fields
    }

@router.get("/validations")
async def list_validations(_user: dict = Depends(verify_token), limit: int = 20, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(select(AIValidation).order_by(AIValidation.created_at.desc()).limit(limit))
    return result.scalars().all()

@router.get("/validations/{validation_id}")
async def get_validation(validation_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    val = await db.get(AIValidation, validation_id)
    if not val:
        raise HTTPException(404, "Validation not found")
    return val

@router.post("/validations/{validation_id}/resolve")
async def resolve_validation(validation_id: int, human_decision: str, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    val = await db.get(AIValidation, validation_id)
    if not val:
        raise HTTPException(404, "Validation not found")
    val.resolved = True
    val.human_decision = human_decision
    await db.commit()
    return {"message": "Resolved"}
