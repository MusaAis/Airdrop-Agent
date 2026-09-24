from fastapi import APIRouter, Depends, HTTPException, status
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import Project, TaskConfig
from backend.projects.manager import (
    create_project, get_project, list_projects, update_project, delete_project,
    create_task_config, list_task_configs, get_task_config, update_task_config, delete_task_config
)
from backend.projects.eligibility import compute_eligibility
from backend.wallet.manager import get_wallet
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectCreate(BaseModel):
    name: str
    type: str  # ecosystem / dapp
    parent_project_id: Optional[int] = None
    chain_ids: List[int] = []
    website: Optional[str] = None
    twitter: Optional[str] = None
    discord: Optional[str] = None
    priority: int = 5
    max_concurrent_wallets: int = 2
    auto_claim_threshold_usd: float = 50.0
    notes: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    max_concurrent_wallets: Optional[int] = None
    chain_ids: Optional[List[int]] = None
    website: Optional[str] = None
    twitter: Optional[str] = None
    discord: Optional[str] = None
    notes: Optional[str] = None

class TaskConfigCreate(BaseModel):
    project_id: int
    task_type: str
    chain_id: int
    parameters: Dict[str, Any] = {}
    dependency_task_ids: List[int] = []
    frequency_mins: int = 120
    slippage_tolerance: float = 0.005
    deadline_mins: int = 20
    min_amount: float
    max_amount: float
    amount_distribution: str = "weighted_low"
    amount_vary_daily: bool = True
    daily_tx_min: int = 2
    daily_tx_max: int = 7
    token_in: Optional[str] = None
    token_out: Optional[str] = None
    bidirectional: bool = False
    token_in_reverse: Optional[str] = None
    token_out_reverse: Optional[str] = None
    contract_label: Optional[str] = None
    enabled: bool = True

class TaskConfigUpdate(BaseModel):
    task_type: Optional[str] = None
    chain_id: Optional[int] = None
    parameters: Optional[Dict] = None
    frequency_mins: Optional[int] = None
    enabled: Optional[bool] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    daily_tx_min: Optional[int] = None
    daily_tx_max: Optional[int] = None
    bidirectional: Optional[bool] = None
    # ... other optional fields

@router.get("/")
async def list_projects_route(_user: dict = Depends(verify_token), status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await list_projects(db, status)

@router.post("/")
async def create_project_route(data: ProjectCreate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    project = await create_project(db, **data.model_dump())
    return project

@router.get("/{project_id}")
async def get_project_route(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    project = await get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project

@router.put("/{project_id}")
async def update_project_route(project_id: int, data: ProjectUpdate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    project = await update_project(db, project_id, **data.model_dump(exclude_unset=True))
    if not project:
        raise HTTPException(404, "Project not found")
    return project

@router.delete("/{project_id}")
async def delete_project_route(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    success = await delete_project(db, project_id)
    if not success:
        raise HTTPException(404, "Project not found")
    return {"message": "Deleted"}

# Task config endpoints
@router.get("/{project_id}/tasks")
async def list_project_tasks(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    tasks = await list_task_configs(db, project_id=project_id)
    return tasks

@router.post("/{project_id}/tasks")
async def create_project_task(project_id: int, data: TaskConfigCreate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    if data.project_id != project_id:
        raise HTTPException(400, "project_id mismatch")
    task = await create_task_config(db, **data.model_dump())
    return task

@router.get("/tasks/{task_id}")
async def get_task_config_route(task_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    task = await get_task_config(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task

@router.put("/tasks/{task_id}")
async def update_task_config_route(task_id: int, data: TaskConfigUpdate, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    task = await update_task_config(db, task_id, **data.model_dump(exclude_unset=True))
    if not task:
        raise HTTPException(404, "Task not found")
    return task

@router.delete("/tasks/{task_id}")
async def delete_task_config_route(task_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    success = await delete_task_config(db, task_id)
    if not success:
        raise HTTPException(404, "Task not found")
    return {"message": "Deleted"}

@router.get("/{project_id}/eligibility/{wallet_id}")
async def wallet_eligibility(project_id: int, wallet_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    wallet = await get_wallet(db, wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")
    result = await compute_eligibility(db, project_id, wallet)
    return result
