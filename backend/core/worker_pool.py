import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from backend.core.daily_targets import get_or_create_daily_target
from typing import Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import async_session
from backend.models import (
    ActiveTask, Wallet, TaskConfig, Project, Chain, AgentStatus, TaskDailyProgress,
    WalletSettings
)
from backend.tasks.swap import SwapTask
from backend.tasks.generic import InteractContractTask
from backend.wallet.manager import get_wallet, get_wallet_settings
from backend.projects.manager import get_project, get_task_config
from backend.chains.manager import get_chain
from backend.core.nonce_manager import lock_nonce, release_nonce
from backend.wallet.balance import get_gas_token_balance
from backend.core.gas_spike_guard import check_gas_spike
from backend.core.memory_guard import is_memory_critical

from backend.tasks.swap import SwapTask
from backend.tasks.generic import InteractContractTask
from backend.tasks.bridge import BridgeTask
from backend.tasks.transfer import TransferTask
from backend.tasks.stake import StakeTask, UnstakeTask
from backend.tasks.liquidity import ProvideLiquidityTask, RemoveLiquidityTask

logger = logging.getLogger("airdrop.worker")

TASK_REGISTRY = {
    "swap": SwapTask,
    "bridge": BridgeTask,
    "transfer": TransferTask,
    "stake": StakeTask,
    "unstake": UnstakeTask,
    "provide_liquidity": ProvideLiquidityTask,
    "remove_liquidity": RemoveLiquidityTask,
    "interact_contract": InteractContractTask,
}

class WorkerPool:
    def __init__(self, max_slots: int = 4):
        self.max_slots = max_slots
        self.slots = [None] * max_slots
        self.lock = asyncio.Lock()
        self.running = False
        self.queue: List[Dict] = []
        self.active_task_ids = set()  # (wallet_id, chain_id) dedup guard
        self.slot_tasks: dict = {}    # slot_id → asyncio.Task (for watchdog respawn)

    async def start(self):
        self.running = True
        for i in range(self.max_slots):
            self.slot_tasks[i] = asyncio.create_task(self._worker(i))

    async def stop(self):
        self.running = False
        # Wait for slots to drain — but never hang forever (fix 3.3)
        timeout = 60
        deadline = time.monotonic() + timeout
        while any(self.slots) and time.monotonic() < deadline:
            await asyncio.sleep(1)
        # If anything is still stuck after timeout, clear slots so we exit
        if any(self.slots):
            logger.warning("WorkerPool.stop(): timeout reached, forcing shutdown")
            self.slots = [None] * self.max_slots

    async def _worker(self, slot_id: int):
        """Continuously pick tasks from the queue and execute them."""
        while self.running:
            task_item = None
            async with self.lock:
                if self.queue:
                    self.queue.sort(key=lambda x: x["priority"], reverse=True)
                    task_item = self.queue.pop(0)
                    self.slots[slot_id] = task_item
            if task_item:
                await self._execute_task(slot_id, task_item)
                async with self.lock:
                    self.slots[slot_id] = None
            else:
                await asyncio.sleep(1)

    async def _execute_task(self, slot_id: int, item: dict):
        """Execute one task, handle timeouts, errors, and cleanup."""
        wallet = item["wallet"]
        task_config = item["task_config"]
        project = item["project"]
        chain = item["chain"]
        key = (wallet.id, chain.id)

        async with async_session() as db:
            # Check if wallet+chain already has a DB active task row
            stmt = select(ActiveTask).where(
                ActiveTask.wallet_id == wallet.id,
                ActiveTask.chain_id == chain.id
            )
            active_exists = (await db.execute(stmt)).scalar_one_or_none()
            if active_exists:
                logger.info(f"Wallet {wallet.id} already has active task on chain {chain.id}")
                async with self.lock:
                    self.active_task_ids.discard(key)  # clean up in-memory set
                return

            # Create active task record
            active_task = ActiveTask(
                wallet_id=wallet.id,
                chain_id=chain.id,
                task_config_id=task_config.id,
                project_id=project.id,
                worker_slot=slot_id,
                started_at=datetime.now(timezone.utc),
                timeout_at=datetime.now(timezone.utc) + timedelta(minutes=8)
            )
            db.add(active_task)
            await db.commit()

            # Memory guard — delete row BEFORE early return (fix 3.2)
            if is_memory_critical():
                logger.warning("Memory critical, pausing task dispatch")
                await db.delete(active_task)
                await db.commit()
                async with self.lock:
                    self.active_task_ids.discard(key)
                return

            # Gas spike guard — same cleanup before early return (fix 3.2)
            if await check_gas_spike(chain):
                logger.info(f"Gas spike on {chain.name}, deferring task")
                await db.delete(active_task)
                await db.commit()
                async with self.lock:
                    self.active_task_ids.discard(key)
                return

            # Build the correct task class
            task_cls = TASK_REGISTRY.get(task_config.task_type)
            if not task_cls:
                logger.error(f"No handler for task type {task_config.task_type}")
                await db.delete(active_task)
                await db.commit()
                async with self.lock:
                    self.active_task_ids.discard(key)
                return

            task_instance = task_cls(task_config, wallet, chain, project, db)

            try:
                result = await asyncio.wait_for(task_instance.execute(), timeout=480)
                if result.get("status") == "success":
                    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    progress = await get_or_create_daily_target(db, wallet.id, wallet.address, project.id, task_config, today_str)
                    progress.completed += 1
                    wallet.failure_count = 0
                    # Reset project-level circuit breaker on success (fix 3.4)
                    if project.consecutive_failures > 0:
                        from backend.projects.circuit_breaker import reset_circuit
                        await reset_circuit(db, project)
                else:
                    wallet.failure_count += 1
                    if wallet.failure_count >= 3:
                        wallet.status = "cooldown"
                    # Increment project-level circuit breaker on failure (fix 3.4)
                    from backend.projects.circuit_breaker import increment_failure
                    await increment_failure(db, project)
                await db.commit()
            except asyncio.TimeoutError:
                logger.error(f"Task timed out after 8 min: wallet={wallet.id} chain={chain.id}")
                await release_nonce(db, wallet.id, chain.id, increment=False)
                wallet.failure_count += 1
                from backend.projects.circuit_breaker import increment_failure
                await increment_failure(db, project)
            except Exception as e:
                logger.error(f"Task execution error: {e}")
                wallet.failure_count += 1
                from backend.projects.circuit_breaker import increment_failure
                await increment_failure(db, project)
            finally:
                # Always remove active task row and in-memory key (fixes 3.1 and 3.2)
                try:
                    await db.delete(active_task)
                    await db.commit()
                except Exception:
                    pass
                async with self.lock:
                    self.active_task_ids.discard(key)

    async def enqueue(self, items: List[Dict]):
        async with self.lock:
            for item in items:
                key = (item["wallet"].id, item["chain"].id)
                if key not in self.active_task_ids:
                    self.queue.append(item)
                    self.active_task_ids.add(key)
