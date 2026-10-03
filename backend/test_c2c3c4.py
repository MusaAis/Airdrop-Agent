import asyncio, os, sys, types, logging
from unittest.mock import AsyncMock, MagicMock
logging.disable(logging.CRITICAL)
from sqlalchemy import select
from backend.database import init_db, async_session
from backend.models import Chain, Project, Wallet, TaskConfig, WalletNonce, AgentStatus

async def seed():
    await init_db()
    async with async_session() as db:
        db.add(Chain(id=1,name="T",chain_id=1,rpc_urls=["http://x"],gas_token_symbol="ETH",gas_token_is_native=True,
                     gas_token_decimals=18,min_gas_balance_warning=0.01,min_gas_balance_critical=0.001))
        db.add(Project(id=1,name="P",type="defi",chain_ids=[1]))
        db.add(Wallet(id=1,address="0x"+"11"*20,is_hd=False,persona={},status="active"))
        db.add(Wallet(id=2,address="0x"+"22"*20,is_hd=False,persona={},status="active"))
        db.add(TaskConfig(id=1,project_id=1,task_type="fake",chain_id=1,parameters={},dependency_task_ids=[],frequency_mins=60,min_amount=1,max_amount=2))
        db.add(AgentStatus(id=1,status="running",current_tasks=[],next_scheduled_tasks=[]))
        await db.commit()

# ------------------------------------------------------------------ C2
async def test_c2():
    import backend.core.worker_pool as wp
    class FailTask:
        def __init__(s,*a,**k): pass
        async def execute(s): return {"status":"failed","reason":"boom"}
    wp.TASK_REGISTRY["fake"]=FailTask
    wp.is_memory_critical=lambda: False
    wp.check_gas_spike=AsyncMock(return_value=False)
    wp.record_failure=AsyncMock()
    pool=wp.WorkerPool()
    for i in range(3):
        # build queue item exactly like queue_manager: objects from a session that is then closed
        async with async_session() as s:
            w=await s.get(Wallet,1); p=await s.get(Project,1); tc=await s.get(TaskConfig,1); ch=await s.get(Chain,1)
        pool.active_task_ids.add((1,1))
        await pool._execute_task(0,{"wallet":w,"project":p,"task_config":tc,"chain":ch,"priority":1})
    async with async_session() as s:
        w=await s.get(Wallet,1); p=await s.get(Project,1)
    print(f"C2  after 3 failed runs -> wallet.failure_count={w.failure_count} wallet.status={w.status} | project.consecutive_failures={p.consecutive_failures}")

# ------------------------------------------------------------------ C3
async def test_c3():
    import backend.core.nonce_manager as nm
    import backend.chains.rpc_pool as rp
    def fake_w3(count=None, fail=False):
        w3=MagicMock()
        async def gtc(addr, block="latest"):
            if fail: raise RuntimeError("rpc down")
            return count
        w3.eth.get_transaction_count=gtc
        return w3
    async def run(wallet_id, count=None, fail=False):
        rp.get_web3=AsyncMock(return_value=fake_w3(count,fail))
        async with async_session() as db:
            n=await nm.lock_nonce(db,wallet_id,1)
            rec=(await db.execute(select(WalletNonce).where(WalletNonce.wallet_id==wallet_id))).scalar_one()
            locked=rec.locked
            await nm.release_nonce(db,wallet_id,1,increment=False)
        return n,locked
    print("C3  fresh record, chain pending count=7 ->", (await run(1,7))[0], "(expected 7)")
    # stored ahead of chain: keep stored
    async with async_session() as db:
        r=(await db.execute(select(WalletNonce).where(WalletNonce.wallet_id==1))).scalar_one(); r.nonce=9; await db.commit()
    print("C3b stored=9, chain=7 ->", (await run(1,7))[0], "(expected 9, max of both)")
    n,locked=await run(2,fail=True)
    print("C3c RPC down, fresh record ->", n, "| lock was taken and released cleanly:", locked is True)

# ------------------------------------------------------------------ C4
async def test_c4():
    import backend.telegram.bot as bot
    import backend.telegram.whitelist as wl
    from backend.config import ALLOWED_USER_IDS
    uid=ALLOWED_USER_IDS[0]
    sent=[]
    class Msg:
        def __init__(s,t): s.text=t
        async def reply_text(s,t,**k): sent.append(t)
    class U:
        def __init__(s,t): s.message=Msg(t); s.effective_user=types.SimpleNamespace(id=uid)
    ctx=types.SimpleNamespace(args=[])
    async def say(t): sent.clear(); await bot.fallback_nl(U(t),ctx); return sent[-1] if sent else None
    async def slash(handler,args):
        sent.clear(); ctx.args=args; await bot.make_cmd(handler)(U("/x"),ctx); return sent[-1]
    async def status(wid):
        async with async_session() as s: return (await s.get(Wallet,wid)).status

    # slash command path: /wallet_pause 1
    r=await slash(bot.handle_wallet_pause,["1"]); print("C4  /wallet_pause 1 ->", r.splitlines()[0][:50], "| status now:", await status(1))
    r=await say("confirm"); print("    reply 'confirm' ->", r[:40], "| status now:", await status(1))
    # slash: /wallet_blacklist 2 then cancel
    await slash(bot.handle_wallet_blacklist,["2"]); r=await say("cancel"); print("    blacklist 2 then 'cancel' ->", r, "| status:", await status(2))
    # slash: blacklist 2 then confirm
    await slash(bot.handle_wallet_blacklist,["2"]); r=await say("confirm"); print("    blacklist 2 then 'confirm' ->", r[:30], "| status:", await status(2))
    # NL/dispatch path
    async with async_session() as db:
        r1=await bot.dispatch_action(uid,"wallet.pause",{"id":1},db)
        print("    dispatch wallet.pause (NL) first reply:", r1.splitlines()[0][:45])
    r=await say("confirm"); print("    ... then 'confirm' ->", r[:35])
    # _CONFIRM_REQUIRED path: nonce.release_all (staged twice in old code)
    async with async_session() as db:
        r1=await bot.dispatch_action(uid,"nonce.release_all",{},db); print("    nonce.release_all first reply:", r1.splitlines()[0][:40])
    r=await say("confirm"); print("    ... then 'confirm' ->", r[:40])
    # agent.kill via staged path
    async with async_session() as db:
        r1=await bot.dispatch_action(uid,"agent.kill",{},db); print("    agent.kill first reply:", r1.splitlines()[0][:40])
    r=await say("confirm"); print("    ... then 'confirm' ->", r.splitlines()[0][:60])
    print("    /agent_kill registered:", hasattr(bot,"agent_kill_cmd"))

async def main():
    await seed()
    await test_c2(); await test_c3(); await test_c4()
asyncio.run(main())
