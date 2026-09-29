import asyncio
import ipaddress
import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import Project, TaskConfig
from backend.projects.manager import (
    create_project, get_project, list_projects, update_project, delete_project,
    create_task_config, list_task_configs, get_task_config, update_task_config, delete_task_config,
    archive_project, restore_project, stop_project, declare_eligibility, clear_eligibility,
)
from backend.projects.eligibility import compute_eligibility
from backend.projects.criteria import list_criteria, upsert_criteria_from_ai
from backend.ai.orchestrator import dual_ai_validate
from backend.ai.prompts import prompt_criteria
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

class CriteriaDraftRequest(BaseModel):
    docs_url: Optional[str] = None
    docs_text: Optional[str] = None  # if the user pastes text instead of a URL

class CriteriaAcceptRequest(BaseModel):
    criteria: List[Dict[str, Any]]  # the (possibly user-edited) draft items to save

class EligibilityDeclareRequest(BaseModel):
    eligible: bool
    value_usd: Optional[float] = None  # only meaningful when eligible=True

@router.get("/")
async def list_projects_route(
    _user: dict = Depends(verify_token),
    status: Optional[str] = None,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Phase 4: archived projects are hidden by default (soft-delete). Pass
    ?include_archived=true or ?status=archived to see them — used by the
    future Phase 7 stats dashboard, not needed for the normal Projects tab.
    """
    return await list_projects(db, status, include_archived=include_archived)

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
    """
    Phase 4: this now soft-archives instead of hard-deleting. Musa's
    requirement is that a "deleted" project stays in the historical record
    (for the Phase 7 stats dashboard) rather than disappearing from the DB.
    Use POST /{project_id}/restore to undo, or see backend/projects/manager.py
    for the (unwired) hard-delete helper if a true delete is ever needed.
    """
    project = await archive_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return {"message": f"Project '{project.name}' archived (soft-deleted) — still visible with ?include_archived=true"}

@router.post("/{project_id}/restore")
async def restore_project_route(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    project = await restore_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return {"message": f"Project '{project.name}' restored to active"}

@router.post("/{project_id}/stop")
async def stop_project_route(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """
    Deliberate manual halt — distinct from archive (stays visible in the
    default project list) and distinct from a circuit-breaker auto-pause
    (this is intentional, not failure-triggered). Farming stops immediately
    since queue_manager.py only dispatches status == 'active' projects.
    """
    project = await stop_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return {"message": f"Project '{project.name}' stopped"}

@router.post("/{project_id}/eligibility")
async def declare_eligibility_route(
    project_id: int, data: EligibilityDeclareRequest,
    _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db),
):
    """
    Website-only control (per Phase 4 scope — Telegram has no setter for
    this, only project.status reads it). Declaring eligible or not_eligible
    either way immediately stops the agent from scheduling any further tasks
    for this project, regardless of its `status` field — see
    queue_manager._project_is_dispatchable().
    """
    project = await declare_eligibility(db, project_id, data.eligible, data.value_usd)
    if not project:
        raise HTTPException(404, "Project not found")
    verdict = "eligible" if data.eligible else "not eligible"
    value_note = f" (est. ${data.value_usd:.2f})" if data.eligible and data.value_usd else ""
    return {"message": f"Project '{project.name}' declared {verdict}{value_note}. Farming stopped for this project."}

@router.post("/{project_id}/eligibility/clear")
async def clear_eligibility_route(project_id: int, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Undo an eligibility declaration (e.g. mis-click). Farming resumes on
    the next queue cycle if the project's status is otherwise active."""
    project = await clear_eligibility(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return {"message": f"Eligibility cleared for '{project.name}' — back to pending."}

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
    """
    NOTE: this is the existing per-wallet CRITERIA-PROGRESS check (how close
    is this wallet to meeting the project's eligibility criteria) — unrelated
    to the new Phase 4 declare_eligibility() outcome flag above, which is a
    single per-project yes/no/pending declared by Musa. Both live under
    "/eligibility" but at different path shapes; kept as-is to avoid breaking
    the existing dashboard call in AddProject.jsx / Projects.jsx.
    """
    wallet = await get_wallet(db, wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")
    result = await compute_eligibility(db, project_id, wallet)
    return result


# ── AI-drafted eligibility criteria (PLAN.md §5.5) ──────────────────────────

async def _assert_public_http_url(url: str) -> None:
    """
    Reject anything that isn't a plain http(s) URL pointing at a public host.
    The draft endpoint makes the server fetch a user-supplied URL, so without
    this it could be aimed at localhost, the cloud metadata service
    (169.254.169.254) or other internal addresses.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(400, "docs_url must be a valid http(s) URL")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, None)
    except Exception:
        raise HTTPException(400, "Could not resolve docs_url host")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(400, "docs_url must point to a public host")


def _html_to_text(html: str) -> str:
    """Crude tag stripper so the AI prompt isn't mostly markup."""
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


@router.post("/{project_id}/criteria/draft")
async def draft_project_criteria(
    project_id: int, data: CriteriaDraftRequest,
    _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)
):
    """
    AI-drafts eligibility criteria for review — never saved automatically.
    The human must separately POST to /criteria/accept to persist anything
    from the draft, consistent with the "AI never auto-creates" boundary in
    PLAN.md §5.3.
    """
    project = await get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not data.docs_url and not data.docs_text:
        raise HTTPException(400, "Provide docs_url or docs_text")

    doc_content = data.docs_text
    if data.docs_url and not doc_content:
        await _assert_public_http_url(data.docs_url)
        try:
            # follow_redirects stays off (httpx default) so a redirect can't
            # bounce the request to an internal address after the check above.
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(data.docs_url, headers={"User-Agent": "AirdropAgent/1.0"})
                resp.raise_for_status()
                doc_content = _html_to_text(resp.text)[:20000]
        except Exception as e:
            raise HTTPException(400, f"Could not fetch docs_url: {e}")

    existing = await list_criteria(db, project_id)
    previous = [c.description for c in existing]

    validation = await dual_ai_validate(
        task_type="criteria",
        system_prompt="You are extracting precise airdrop eligibility criteria. Accuracy is critical — this drives real transactions.",
        user_prompt=prompt_criteria(doc_content, str(previous)),
        db=db,
    )
    decision = validation.final_decision or {}
    return {
        "validation_id": validation.id,
        "agreement_score": validation.agreement_score,
        "requires_human": validation.requires_human,
        "draft_criteria": decision.get("criteria", []),
        "information_gaps": decision.get("information_gaps", []),
        "unconfirmed_rumors": decision.get("unconfirmed_rumors", []),
    }


@router.post("/{project_id}/criteria/accept")
async def accept_project_criteria(
    project_id: int, data: CriteriaAcceptRequest,
    _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)
):
    """
    Persist criteria the human has reviewed (and optionally edited) from a
    prior /criteria/draft call. This is the only path that writes AI-drafted
    criteria to the DB — draft() never does.
    """
    project = await get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    added = await upsert_criteria_from_ai(db, project_id, data.criteria)
    return {"message": f"Added {len(added)} criteria", "added_ids": [c.id for c in added]}
