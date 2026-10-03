"""
Tests for human-like pacing (review item H4).
Run from the repo root:   python3 -m backend.test_scheduling
"""
import asyncio, logging, os, random, sys, tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/t.db",
    "MASTER_PASSWORD": "correct-horse-battery-staple",
    "SECRET_KEY": "k" * 48,
    "TELEGRAM_ALLOWED_USER_IDS": '["42"]',
})
logging.disable(logging.CRITICAL)

from sqlalchemy import select
from backend.database import init_db, async_session
from backend.models import (Chain, Project, TaskConfig, Wallet, WalletSettings, TaskSchedule, ActiveTask)
import backend.core.scheduling as sch
from backend.core.scheduling import record_attempt, task_delay_minutes, utcnow_naive
from backend.core.queue_manager import _get_project_candidates, fill_queue
from backend.core.worker_pool import WorkerPool
import backend.core.worker_pool as wp
from backend.wallet.behavior_randomizer import (
    active_window_start, day_start_offset_minutes, has_started_for_the_day)

_results = []


def check(name, cond, extra=""):
    _results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))


def S(**kw):
    base = dict(active_hour_start=None, active_hour_end=None, start_offset_max_mins=45,
                sleep_min_mins=2, sleep_max_mins=8)
    base.update(kw)
    return SimpleNamespace(**base)


async def seed(n_wallets=3, freq=60, two_chains=False):
    """Fresh rows each call. Returns ids."""
    async with async_session() as db:
        for m in (TaskSchedule, ActiveTask, TaskConfig, WalletSettings, Wallet, Project, Chain):
            for row in (await db.execute(select(m))).scalars().all():
                await db.delete(row)
        await db.commit()
        chains = []
        for i in range(2 if two_chains else 1):
            c = Chain(name=f"C{i}", chain_id=100 + i, rpc_urls=[], gas_token_symbol="ETH", gas_token_is_native=True,
                      gas_token_decimals=18, min_gas_balance_warning=0.01, min_gas_balance_critical=0.001, enabled=True)
            db.add(c); chains.append(c)
        proj = Project(name="P", type="testnet", chain_ids=[], status="active", priority=5, max_concurrent_wallets=10)
        db.add(proj)
        await db.flush()
        tcs = []
        for c in chains:
            tc = TaskConfig(project_id=proj.id, task_type="transfer", chain_id=c.id, parameters={}, dependency_task_ids=[],
                            frequency_mins=freq, enabled=True, min_amount=0.1, max_amount=0.2,
                            daily_tx_min=50, daily_tx_max=50)
            db.add(tc); tcs.append(tc)
        wallets = []
        for i in range(n_wallets):
            w = Wallet(address=f"0x{i:040x}", is_hd=False, persona={}, status="active")
            db.add(w); wallets.append(w)
        await db.flush()
        for w in wallets:     # no active window, no offset: isolate the rule under test
            db.add(WalletSettings(wallet_id=w.id, start_offset_max_mins=0, sleep_min_mins=2, sleep_max_mins=8))
        await db.commit()
        return proj.id, [t.id for t in tcs], [w.id for w in wallets], [c.id for c in chains]


async def candidates(proj_id):
    async with async_session() as db:
        p = await db.get(Project, proj_id)
        return await _get_project_candidates(db, p, SimpleNamespace(max_slots=4, slots=[None] * 4))


async def main():
    await init_db()

    # ---------- pure functions
    rng = random.Random(1)
    s_ = [task_delay_minutes("success", 120, rng) for _ in range(500)]
    check("success delay = frequency x [0.8, 1.4]", all(96 <= x <= 168 for x in s_) and max(s_) - min(s_) > 20)
    f_ = [task_delay_minutes("failed", 120, rng) for _ in range(500)]
    check("failed backoff ~10 min x [0.8, 1.5]", all(8 <= x <= 15 for x in f_))
    k_ = [task_delay_minutes("skipped", 120, rng) for _ in range(500)]
    check("skipped backoff 3-8 min", all(3 <= x <= 8 for x in k_))
    check("None / 0 frequency falls back safely", task_delay_minutes("success", None, rng) >= 96
          and task_delay_minutes("success", 0, rng) > 0)
    try:
        task_delay_minutes("simulated", 60); ok = False
    except ValueError:
        ok = True
    check("unknown outcome is rejected", ok)

    # ---------- start offset
    now = datetime(2026, 10, 3, 9, 30, tzinfo=timezone.utc)
    st = S(active_hour_start=8, active_hour_end=20, start_offset_max_mins=60)
    ws = active_window_start(st, now)
    check("window start = today 08:00 UTC", ws == datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc))
    o1 = day_start_offset_minutes(st, 1, ws)
    check("offset is deterministic per wallet+day", o1 == day_start_offset_minutes(st, 1, ws))
    offs = {day_start_offset_minutes(st, w, ws) for w in range(1, 40)}
    check("offsets differ between wallets and stay within [0, max]", len(offs) > 10 and min(offs) >= 0 and max(offs) <= 60)
    check("offset differs across days", len({day_start_offset_minutes(st, 1, ws + timedelta(days=d)) for d in range(20)}) > 5)
    off = day_start_offset_minutes(st, 1, ws)
    before = ws + timedelta(minutes=off) - timedelta(seconds=1)
    after = ws + timedelta(minutes=off)
    check("wallet waits out its offset, then starts", not has_started_for_the_day(st, 1, before) and has_started_for_the_day(st, 1, after))
    wrap = S(active_hour_start=22, active_hour_end=6, start_offset_max_mins=30)
    n3 = datetime(2026, 10, 3, 3, 0, tzinfo=timezone.utc)
    check("wrapped window at 03:00 started yesterday 22:00", active_window_start(wrap, n3) == datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc))
    check("no window configured -> always started", has_started_for_the_day(S(), 1, now) and has_started_for_the_day(None, 1, now))

    # ---------- candidate gating
    proj, tcs, wals, chs = await seed(n_wallets=3, freq=60)
    c = await candidates(proj)
    check("fresh wallets are all candidates", len(c) == 3, str(len(c)))

    async with async_session() as db:
        tc = await db.get(TaskConfig, tcs[0])
        await record_attempt(db, wals[0], tc, "success")
    c = await candidates(proj)
    check("wallet that just ran is NOT a candidate (sleep + frequency)", {x["wallet"].id for x in c} == set(wals[1:]), str({x["wallet"].id for x in c}))

    async with async_session() as db:
        row = (await db.execute(select(TaskSchedule))).scalar_one()
        w = await db.get(Wallet, wals[0])
        check("TaskSchedule row written (last_run_at set)", row.last_run_at is not None and row.next_run_at > utcnow_naive() + timedelta(minutes=40))
        check("wallet.next_available_at is 2-8 min ahead",
              timedelta(minutes=1.9) < w.next_available_at - utcnow_naive() < timedelta(minutes=8.1))
        w.next_available_at = utcnow_naive() - timedelta(seconds=1)       # sleep over, task still not due
        await db.commit()
    c = await candidates(proj)
    check("sleep over but frequency not elapsed -> still blocked", wals[0] not in {x["wallet"].id for x in c})
    async with async_session() as db:
        row = (await db.execute(select(TaskSchedule))).scalar_one()
        row.next_run_at = utcnow_naive() - timedelta(seconds=1)
        await db.commit()
    c = await candidates(proj)
    check("both elapsed -> eligible again", wals[0] in {x["wallet"].id for x in c})

    async with async_session() as db:      # second attempt updates the same row (upsert)
        tc = await db.get(TaskConfig, tcs[0])
        await record_attempt(db, wals[0], tc, "failed")
        n = len((await db.execute(select(TaskSchedule))).scalars().all())
        row = (await db.execute(select(TaskSchedule))).scalar_one()
    check("record_attempt upserts (one row per wallet+task)", n == 1)
    check("failed attempt backs off ~10 min, not a full frequency", row.next_run_at - utcnow_naive() < timedelta(minutes=16))

    async with async_session() as db:
        tc = await db.get(TaskConfig, tcs[0])
        before = len((await db.execute(select(TaskSchedule))).scalars().all())
        await record_attempt(db, wals[1], tc, "simulated")
        await record_attempt(db, wals[1], tc, "bogus")
        after = len((await db.execute(select(TaskSchedule))).scalars().all())
    check("simulated / unknown outcomes never touch the schedule", before == after)
    async with async_session() as db:
        await record_attempt(db, 99999, SimpleNamespace(id=1, frequency_mins=60), "success")
    check("record_attempt never raises on bad input", True)

    # personal start offset gates candidates
    proj, tcs, wals, chs = await seed(n_wallets=1, freq=60)
    hr = datetime.now(timezone.utc).hour
    async with async_session() as db:
        st_row = (await db.execute(select(WalletSettings))).scalar_one()
        st_row.active_hour_start = hr
        st_row.active_hour_end = (hr + 3) % 24 if (hr + 3) % 24 > hr else 23
        st_row.start_offset_max_mins = 59
        await db.commit()
    nowu = datetime.now(timezone.utc)
    ws_ = active_window_start(SimpleNamespace(active_hour_start=hr, active_hour_end=24 if hr > 20 else hr + 3,
                                              start_offset_max_mins=59), nowu)
    expect = nowu >= ws_ + timedelta(minutes=day_start_offset_minutes(SimpleNamespace(start_offset_max_mins=59), wals[0], ws_))
    c = await candidates(proj)
    check("candidate list agrees with the start-offset rule", (len(c) == 1) == expect, f"expect={expect} got={len(c)}")

    # one candidate per wallet even with two due tasks on two chains
    proj, tcs, wals, chs = await seed(n_wallets=3, freq=60, two_chains=True)
    c = await candidates(proj)
    ids = [x["wallet"].id for x in c]
    check("one candidate per wallet (2 chains x 3 wallets -> 3)", len(c) == 3 and len(set(ids)) == 3, str(ids))

    # ---------- fill_queue: global dedupe, last_selected_at, no blocking sleep
    class FakePool:
        max_slots = 4
        slots = [None] * 4
        def __init__(self): self.items = []
        async def enqueue(self, items): self.items.extend(items)
    pool = FakePool()
    import time
    t0 = time.monotonic()
    await fill_queue(pool)
    check("fill_queue enqueues one task per wallet", len(pool.items) == 3 and len({i["wallet"].id for i in pool.items}) == 3)
    check("fill_queue no longer sleeps between items", time.monotonic() - t0 < 5)
    async with async_session() as db:
        ls = [(await db.get(Wallet, w)).last_selected_at for w in wals]
    check("last_selected_at is now written for selected wallets", all(x is not None for x in ls))
    # naive/aware mix used to be a latent TypeError once the column was set
    c = await candidates(proj)
    check("candidate sort works with last_selected_at set", len(c) == 3)

    # second project sharing the same wallets must not double-book them
    async with async_session() as db:
        p2 = Project(name="P2", type="testnet", chain_ids=[], status="active", priority=5, max_concurrent_wallets=10)
        db.add(p2); await db.flush()
        db.add(TaskConfig(project_id=p2.id, task_type="transfer", chain_id=chs[0], parameters={}, dependency_task_ids=[],
                          frequency_mins=60, enabled=True, min_amount=0.1, max_amount=0.2, daily_tx_min=50, daily_tx_max=50))
        await db.commit()
    pool2 = FakePool()
    pool2.max_slots = 8; pool2.slots = [None] * 8
    await fill_queue(pool2)
    check("a wallet is never selected by two projects in one fill",
          len({i["wallet"].id for i in pool2.items}) == len(pool2.items), str([i["wallet"].id for i in pool2.items]))

    # ---------- real worker path with fake tasks
    proj, tcs, wals, chs = await seed(n_wallets=4, freq=90)
    outcomes = iter(["success", "failed", "skipped", "simulated"])

    class FakeTask:
        def __init__(self, *a, **k): pass
        async def execute(self):
            return {"status": next(outcomes), "reason": "x", "tx_hash": "0xabc"}
    wp.TASK_REGISTRY["transfer"] = FakeTask
    wp.check_gas_spike = lambda chain: _false()
    wp.is_memory_critical = lambda: False
    pool = WorkerPool(max_slots=1)
    async with async_session() as db:
        project = await db.get(Project, proj); tcfg = await db.get(TaskConfig, tcs[0]); chain = await db.get(Chain, chs[0])
        ws_objs = [await db.get(Wallet, w) for w in wals]
    seen = {}
    for w, expected in zip(ws_objs, ["success", "failed", "skipped", "simulated"]):
        pool.active_task_ids.add((w.id, chain.id))
        await pool._execute_task(0, {"wallet": w, "task_config": tcfg, "project": project, "chain": chain, "priority": 5})
        async with async_session() as db:
            row = (await db.execute(select(TaskSchedule).where(TaskSchedule.wallet_id == w.id))).scalar_one_or_none()
            wl = await db.get(Wallet, w.id)
        seen[expected] = (row, wl)
    r, wl = seen["success"]
    check("worker: success schedules next run ~frequency out", r and timedelta(minutes=70) < r.next_run_at - utcnow_naive() < timedelta(minutes=130))
    check("worker: success sets wallet sleep + last_active", wl.next_available_at and wl.last_active)
    r, wl = seen["failed"]
    check("worker: failure schedules a ~10 min backoff", r and r.next_run_at - utcnow_naive() < timedelta(minutes=16))
    r, wl = seen["skipped"]
    check("worker: skip schedules a short 3-8 min deferral", r and r.next_run_at - utcnow_naive() < timedelta(minutes=9))
    r, wl = seen["simulated"]
    check("worker: dry-run result leaves the schedule untouched", r is None and wl.next_available_at is None)

    # gas-spike early return also backs off
    wp.check_gas_spike = lambda chain: _true()
    w = ws_objs[3]
    pool.active_task_ids.add((w.id, chain.id))
    await pool._execute_task(0, {"wallet": w, "task_config": tcfg, "project": project, "chain": chain, "priority": 5})
    async with async_session() as db:
        row = (await db.execute(select(TaskSchedule).where(TaskSchedule.wallet_id == w.id))).scalar_one_or_none()
    check("worker: gas-spike deferral also backs off (was a 30 s retry loop)", row is not None and row.next_run_at - utcnow_naive() < timedelta(minutes=9))

    failed = [n for n, ok in _results if not ok]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} passed")
    if failed:
        print("FAILED:", *failed, sep="\n  ")
        sys.exit(1)


async def _false(): return False
async def _true(): return True

if __name__ == "__main__":
    asyncio.run(main())
