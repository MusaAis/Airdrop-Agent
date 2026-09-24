"""
CRUD operations for project eligibility criteria.
"""
import logging
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import ProjectCriteria

logger = logging.getLogger("airdrop.projects.criteria")


async def add_criterion(
    db: AsyncSession,
    project_id: int,
    type: str,
    description: str,
    threshold: Optional[float] = None,
    unit: Optional[str] = None,
    chain_id: Optional[int] = None,
    contract_address: Optional[str] = None,
    source_quote: Optional[str] = None,
    uncertain: bool = False,
    ai_extracted: bool = True,
) -> ProjectCriteria:
    criterion = ProjectCriteria(
        project_id=project_id,
        type=type,
        description=description,
        threshold=threshold,
        unit=unit,
        chain_id=chain_id,
        contract_address=contract_address,
        source_quote=source_quote,
        uncertain=uncertain,
        ai_extracted=ai_extracted,
    )
    db.add(criterion)
    await db.commit()
    await db.refresh(criterion)
    logger.info(f"Criterion added for project {project_id}: {description[:50]}")
    return criterion


async def list_criteria(
    db: AsyncSession, project_id: int, include_uncertain: bool = True
) -> List[ProjectCriteria]:
    stmt = select(ProjectCriteria).where(ProjectCriteria.project_id == project_id)
    if not include_uncertain:
        stmt = stmt.where(ProjectCriteria.uncertain == False)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_criterion(db: AsyncSession, criterion_id: int) -> Optional[ProjectCriteria]:
    return await db.get(ProjectCriteria, criterion_id)


async def update_criterion(
    db: AsyncSession,
    criterion_id: int,
    **kwargs,
) -> Optional[ProjectCriteria]:
    criterion = await db.get(ProjectCriteria, criterion_id)
    if not criterion:
        return None
    for key, value in kwargs.items():
        if hasattr(criterion, key) and value is not None:
            setattr(criterion, key, value)
    criterion.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(criterion)
    return criterion


async def delete_criterion(db: AsyncSession, criterion_id: int) -> bool:
    criterion = await db.get(ProjectCriteria, criterion_id)
    if not criterion:
        return False
    await db.delete(criterion)
    await db.commit()
    return True


async def upsert_criteria_from_ai(
    db: AsyncSession, project_id: int, criteria_list: List[dict]
) -> List[ProjectCriteria]:
    """
    Bulk-insert criteria extracted by AI. Skips duplicates by description.
    """
    existing = await list_criteria(db, project_id)
    existing_descs = {c.description for c in existing}
    added = []
    for c in criteria_list:
        desc = c.get("description", "")
        if desc in existing_descs:
            continue
        added.append(await add_criterion(
            db=db,
            project_id=project_id,
            type=c.get("type", "other"),
            description=desc,
            threshold=c.get("threshold"),
            unit=c.get("unit"),
            source_quote=c.get("source_quote"),
            uncertain=c.get("uncertain", False),
            ai_extracted=True,
        ))
    logger.info(f"Bulk criteria upsert for project {project_id}: {len(added)} added")
    return added

