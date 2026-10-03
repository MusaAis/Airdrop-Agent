"""
Tests for persisted emergency stop / dry-run (ROADMAP item 1).
Run from the repo root:   python3 -m backend.test_killswitch_persist
"""
import asyncio, logging, os, subprocess, sys, tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/t.db",
    "MASTER_PASSWORD": "correct-horse-battery-staple",
    "SECRET_KEY": "k" * 48,
    "TELEGRAM_ALLOWED_USER_IDS": '["42"]',
})
logging.disable(logging.CRITICAL)

import httpx
from sqlalchemy import select, text
import backend.core.kill_switch as ks
from backend.database import init_db, async_session, engine
from backend.models import User, AgentStatus
from backend.security.auth import get_password_hash
from backend.main import app

PW = os.environ["MASTER_PASSWORD"]
_results = []


def check(name, cond, extra=""):
    _results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))


def simulate_restart():
    """Forget all in-memory state, exactly like a new process would."""
    ks._EMERGENCY_STOP = False
    ks.EMERGENCY_STOP = False
    ks.set_dry_run(False)


async def row():
    async with async_session() as db:
        return await db.get(ks.KillSwitchState, 1)


async def main():
    await init_db()
    async with async_session() as db:
        db.add(User(username="admin", hashed_password=get_password_hash(PW)))
        db.add(AgentStatus(id=1, status="running", current_tasks={}, next_scheduled_tasks={}))
        await db.commit()

    # fresh DB, no env: both off
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("fresh start: emergency off, dry-run off", not ks.is_emergency_stop() and not ks.is_dry_run())

    # emergency stop survives a restart
    async with async_session() as db:
        await ks.activate_kill_switch(db, reason="test kill")
    r = await row()
    check("kill is written to the DB", r and r.emergency_stop and r.updated_by == "test kill")
    simulate_restart()
    check("(sanity) memory really was reset", not ks.is_emergency_stop())
    await ks.load_kill_switch_state(env_dry_run=False)
    check("emergency stop is restored after restart", ks.is_emergency_stop())

    async with async_session() as db:
        await ks.deactivate_kill_switch(db)
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("clearing the stop is also persisted", not ks.is_emergency_stop())

    # dry-run survives a restart
    async with async_session() as db:
        await ks.set_dry_run_persistent(db, True, by="test")
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("dry-run ON is restored after restart", ks.is_dry_run())
    async with async_session() as db:
        await ks.set_dry_run_persistent(db, False, by="test")
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("dry-run OFF is restored after restart", not ks.is_dry_run())

    # env DRY_RUN_MODE forces ON at boot, never forces OFF
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=True)
    check("DRY_RUN_MODE=true forces dry-run on at boot", ks.is_dry_run())
    r = await row()
    check("...and that is saved (dashboard shows the truth)", r.dry_run)
    async with async_session() as db:
        await ks.set_dry_run_persistent(db, False, by="test")
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=True)
    check("DRY_RUN_MODE=true overrides a saved OFF at next boot", ks.is_dry_run())
    async with async_session() as db:
        await ks.set_dry_run_persistent(db, False, by="test")
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("env false never forces dry-run off (saved value rules)", not ks.is_dry_run())
    async with async_session() as db:
        await ks.set_dry_run_persistent(db, True, by="test")
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("env false does not turn a saved ON off", ks.is_dry_run())
    async with async_session() as db:
        await ks.set_dry_run_persistent(db, False, by="test")

    # HTTP + Telegram paths write through
    t = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=t, base_url="http://t") as c:
        tok = (await c.post("/auth/login", json={"username": "admin", "password": PW})).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        r = await c.post("/ops/system/dry-run", json={"enabled": True}, headers=h)
        check("POST /ops/system/dry-run turns it on", r.status_code == 200 and r.json()["dry_run"] is True, r.text)
        simulate_restart()
        await ks.load_kill_switch_state(env_dry_run=False)
        check("...and it survives a restart", ks.is_dry_run())
        r = await c.post("/agent/kill?reason=test", headers=h)
        check("POST /agent/kill works", r.status_code == 200, r.text)
        simulate_restart()
        await ks.load_kill_switch_state(env_dry_run=False)
        check("API kill survives a restart", ks.is_emergency_stop())
        r = await c.post("/ops/system/emergency/clear", headers=h)
        check("POST /ops/system/emergency/clear returns state", r.status_code == 200 and r.json()["emergency_stop"] is False, r.text)
        simulate_restart()
        await ks.load_kill_switch_state(env_dry_run=False)
        check("API clear survives a restart", not ks.is_emergency_stop() and ks.is_dry_run())
        await c.post("/ops/system/dry-run", json={"enabled": False}, headers=h)

    from backend.telegram.commands import agent as tg
    async with async_session() as db:
        msg = await tg.handle_agent_dryrun_on(42, db)
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("Telegram /agent_dryrun_on persists", ks.is_dry_run() and "saved" in msg)
    async with async_session() as db:
        await tg.handle_agent_dryrun_off(42, db)
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("Telegram dry-run off persists", not ks.is_dry_run())

    # fail safe if the state table cannot be read
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE kill_switch_state RENAME TO kill_switch_state_x"))
    simulate_restart()
    await ks.load_kill_switch_state(env_dry_run=False)
    check("unreadable state -> fail SAFE (emergency stop + dry-run)", ks.is_emergency_stop() and ks.is_dry_run())
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE kill_switch_state_x RENAME TO kill_switch_state"))

    # real app startup in a fresh process: saved state is applied before the agent loop starts
    db_path = f"{_tmp}/boot.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}", "DRY_RUN_MODE": "false"}
    code = (
        "import asyncio\n"
        "from backend.main import startup\n"
        "from backend.database import init_db, async_session\n"
        "import backend.core.kill_switch as ks\n"
        "async def go():\n"
        "    await init_db()\n"
        "    async with async_session() as db:\n"
        "        await ks.activate_kill_switch(db, 'pre-seeded')\n"
        "        await ks.set_dry_run_persistent(db, True, 'pre-seeded')\n"
        "    ks._EMERGENCY_STOP=False; ks.set_dry_run(False)\n"
        "    await startup()\n"
        "    print('STATE', ks.is_emergency_stop(), ks.is_dry_run())\n"
        "asyncio.run(go())\n"
    )
    p = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=90)
    check("app startup() restores saved emergency stop + dry-run", "STATE True True" in p.stdout, (p.stdout + p.stderr)[-300:])

    failed = [n for n, ok in _results if not ok]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} passed")
    if failed:
        print("FAILED:", *failed, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
