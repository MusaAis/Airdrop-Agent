from fastapi import APIRouter, Depends, HTTPException
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import AIValidation
from backend.ai.orchestrator import dual_ai_validate
from backend.ai.prompts import prompt_discovery, prompt_risk, prompt_criteria, prompt_telegram_cmd, prompt_sybil, prompt_roi, prompt_gap, prompt_config_validation
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/ai", tags=["ai"])

class AIRequest(BaseModel):
    task_type: str  # discovery/risk/criteria/telegram/sybil/roi/gap/config
    input_data: str
    extra_data: Optional[str] = None

@router.post("/validate")
async def validate_with_ai(req: AIRequest, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    prompt_map = {
        "discovery": prompt_discovery,
        "risk": prompt_risk,
        "criteria": prompt_criteria,
        "telegram": prompt_telegram_cmd,
        "sybil": prompt_sybil,
        "roi": prompt_roi,
        "gap": prompt_gap,
        "config": prompt_config_validation,
    }
    if req.task_type not in prompt_map:
        raise HTTPException(400, f"Unknown task type. Choose from {list(prompt_map.keys())}")
    if req.task_type in ["gap", "config", "criteria"] and not req.extra_data:
        raise HTTPException(400, "extra_data required for this task type")
    user_prompt = prompt_map[req.task_type](req.input_data) if req.task_type in ["discovery", "risk", "telegram", "sybil", "roi"] else prompt_map[req.task_type](req.input_data, req.extra_data)
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

@router.get("/discovery/runs")
async def list_discovery_runs(_user: dict = Depends(verify_token), limit: int = 20, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from backend.models import DiscoveryRun
    result = await db.execute(select(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(limit))
    runs = result.scalars().all()
    return [
        {
            "id": r.id, "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "trigger": r.trigger, "status": r.status,
            "sources_scraped": r.sources_scraped, "raw_results_found": r.raw_results_found,
            "new_projects_validated": r.new_projects_validated, "error_message": r.error_message,
        }
        for r in runs
    ]


@router.get("/discovery/next-run")
async def next_discovery_run(_user: dict = Depends(verify_token)):
    from backend.core.scheduler import get_scheduler
    sched = get_scheduler()
    job = sched.get_job("discovery")
    if not job or not job.next_run_time:
        return {"next_run_at": None}
    return {"next_run_at": job.next_run_time.isoformat()}


@router.post("/discovery/run-now")
async def trigger_discovery_now(_user: dict = Depends(verify_token)):
    from backend.core.scheduler import _run_discovery
    await _run_discovery(trigger="manual")
    return {"message": "Discovery scan triggered"}
