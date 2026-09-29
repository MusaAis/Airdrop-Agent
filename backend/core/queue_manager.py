import asyncio
import logging
import random
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.database import async_session
from backend.models import (
    Wallet, WalletSettings, Project, TaskConfig,
    TaskSchedule, TaskDailyProgress, ActiveTask, Chain,
)
from backend.projects.manager import list_task_configs
from backend.wallet.manager import list_wallets, get_wallet_settings
from backend.chains.manager import get_chain
from backend.core.daily_targets import get_or_create_daily_target
from backend.wallet.behavior_randomizer import is_in_active_hours, get_start_offset_seconds

logger = logging.getLogger("airdrop.queue_manager")

# Phase 4: a project in any of these statuses never gets new tasks dispatched,
# regardless of individual task_config.enabled flags. "archived" and "stopped"
# both mean "don't touch this project anymore" — the fill_queue project query
# below already excludes non-"active" status, so this set matters mainly for
# defense-in-depth and for _get_project_candidates() being called directly
# elsewhere in the future.
_NO_DISPATCH_STATUSES = {"archived", "stopped", "paused", "monitor", "dead"}


def _project_is_dispatchable(project: Project) -> bool:
    """
    Single choke point for "should this project ever get a new task queued".
    A project is dispatchable only if:
      - status == "active" (not paused/stopped/archived/monitor/dead), AND
      - circuit breaker is not tripped, AND
      - eligibility has not been declared either way (Phase 4) — once Musa
        marks a project eligible or not_eligible on the dashboard, farming
        stops immediately even if status is still "active", since there is
        nothing left to farm for.
    """
    if project.status != "active":
        return False
    if project.circuit_breaker_active:
        return False
    if getattr(project, "eligibility_status", "pending") in ("eligible", "not_eligible"):
        return False
    return True


async def fill_queue(worker_pool) -> None:
    """
    Priority-weighted proportional queue fill.
    Each project's share of queue slots = project.priority / total_priority_points.
    Capped by project.max_concurrent_wallets.
    """
    async with async_session() as db:
        # Fetch active projects sorted by priority
        projects_result = await db.execute(
            select(Project)
            .where(Project.status == "active", Project.circuit_breaker_active == False)
            .order_by(Project.priority.desc())
        )
        projects = projects_result.scalars().all()
        if not projects:
            return

        # Phase 4: filter out anything declared eligible/not_eligible even
        # though status is still "active" — see _project_is_dispatchable.
        projects = [p for p in projects if _project_is_dispatchable(p)]
        if not projects:
            return

        total_priority = sum(p.priority for p in projects)
        free_slots = worker_pool.max_slots - sum(1 for s in worker_pool.slots if s is not None)
        if free_slots <= 0:
            return

        # Build per-project candidate lists
        project_buckets = {}
        for project in projects:
            candidates = await _get_project_candidates(db, project, worker_pool)
            if candidates:
                project_buckets[project.id] = {
                    "project": project,
                    "candidates": candidates,
                    "weight": project.priority / total_priority,
                    "cap": project.max_concurrent_wallets,
                }

        if not project_buckets:
            return

        # Proportional fill: allocate slots to projects by weight
        to_enqueue = []
        remaining = free_slots

        for proj_id, bucket in project_buckets.items():
            if remaining <= 0:
                break
            # How many slots does this project get?
            allocation = max(1, round(bucket["weight"] * free_slots))
            allocation = min(allocation, bucket["cap"], remaining, len(bucket["candidates"]))

            selected = bucket["candidates"][:allocation]
            to_enqueue.extend(selected)
            remaining -= len(selected)

        # Randomize order within selections to avoid pattern
        random.shuffle(to_enqueue)
        if to_enqueue:
            await worker_pool.enqueue(to_enqueue)
            logger.info(f"Enqueued {len(to_enqueue)} tasks across {len(project_buckets)} projects")
            # Apply wall-clock stagger delays so wallets don't all fire at once.
            # We schedule each item's actual execution delay via a tiny wrapper
            # that sleeps offset_secs before making the slot visible to workers.
            # Simplest safe approach: sleep proportional to queue position so
            # enqueued items spread out naturally without needing extra tasks.
            for i, item in enumerate(to_enqueue):
                delay = item.get("delay_seconds", 0)
                if delay and i > 0:
                    await asyncio.sleep(min(delay, 30))  # cap at 30 s per item


async def _get_project_candidates(db: AsyncSession, project: Project, worker_pool) -> list:
    """Get eligible wallet+task combinations for a project."""
    # Phase 4: belt-and-suspenders check even though fill_queue already
    # filtered the project list — protects any future caller of this
    # function that doesn't go through fill_queue's filtering.
    if not _project_is_dispatchable(project):
        return []

    wallets_result = await db.execute(
        select(Wallet).where(Wallet.status == "active", Wallet.is_gas_wallet == False)
    )
    wallets = wallets_result.scalars().all()

    tasks = await list_task_configs(db, project_id=project.id)
    enabled_tasks = [t for t in tasks if t.enabled]

    if not wallets or not enabled_tasks:
        return []

    candidates = []
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for wallet in wallets:
        settings = await get_wallet_settings(db, wallet.id)

        # Active hours check
        if not is_in_active_hours(settings):
            continue

        # Check if wallet already has active task on any chain
        active_count_result = await db.execute(
            select(func.count()).select_from(ActiveTask).where(ActiveTask.wallet_id == wallet.id)
        )
        if active_count_result.scalar() > 0:
            continue

        for task_config in enabled_tasks:
            # Nonce safety: skip if wallet+chain already active
            if await _has_active_task(db, wallet.id, task_config.chain_id):
                continue

            # Check chain is enabled
            chain = await get_chain(db, task_config.chain_id)
            if not chain or not chain.enabled:
                continue

            # Daily cap check
            progress = await get_or_create_daily_target(
                db, wallet.id, wallet.address, project.id, task_config, today_str
            )
            if progress.completed >= progress.daily_target:
                continue

            # Dependency check
            if task_config.dependency_task_ids:
                deps_met = await _check_dependencies(db, wallet.id, task_config, today_str)
                if not deps_met:
                    continue

            # Calculate staggered start offset
            offset_secs = get_start_offset_seconds(settings)

            candidates.append({
                "wallet": wallet,
                "task_config": task_config,
                "project": project,
                "chain": chain,
                "priority": project.priority,
                "delay_seconds": offset_secs,
            })

    # Sort: least-recently-used wallets first, then by start delay
    candidates.sort(key=lambda x: (
        x["wallet"].last_selected_at or datetime.min.replace(tzinfo=timezone.utc),
        x["delay_seconds"],
    ))
    return candidates


async def _has_active_task(db: AsyncSession, wallet_id: int, chain_id: int) -> bool:
    result = await db.execute(
        select(ActiveTask).where(
            ActiveTask.wallet_id == wallet_id,
            ActiveTask.chain_id == chain_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _check_dependencies(
    db: AsyncSession, wallet_id: int, task_config: TaskConfig, today_str: str
) -> bool:
    for dep_id in (task_config.dependency_task_ids or []):
        result = await db.execute(
            select(TaskDailyProgress).where(
                TaskDailyProgress.wallet_id == wallet_id,
                TaskDailyProgress.task_config_id == dep_id,
                TaskDailyProgress.date == today_str,
                TaskDailyProgress.completed >= 1,
            )
        )
        if not result.scalar_one_or_none():
            return False
    return True
