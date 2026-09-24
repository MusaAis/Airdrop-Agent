from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import CompletedProjectsBlacklist

async def blacklist_project(db: AsyncSession, name: str, reason: str, added_by: str = "ai"):
    entry = CompletedProjectsBlacklist(project_name=name, reason=reason, added_by=added_by)
    db.add(entry)
    await db.commit()
    return entry

async def is_blacklisted(db: AsyncSession, name: str) -> bool:
    from sqlalchemy import select
    result = await db.execute(select(CompletedProjectsBlacklist).where(CompletedProjectsBlacklist.project_name == name))
    return result.scalar_one_or_none() is not None
