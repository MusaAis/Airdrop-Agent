"""
Tests for native-gas reporting (ROADMAP item 3).
Run from the repo root:   python3 -m backend.test_native_gas
"""
import asyncio, logging, os, sys, tempfile
from datetime import datetime, timedelta

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/t.db",
    "MASTER_PASSWORD": "correct-horse-battery-staple",
    "SECRET_KEY": "k" * 48,
    "TELEGRAM_ALLOWED_USER_IDS": '["42"]',
})
logging.disable(logging.CRITICAL)

import httpx
from backend.database import init_db, async_session
from backend.models import Chain, Project, TaskConfig, Wallet, Transaction, User
from backend.security.auth import get_password_hash
from backend.reports.gas_native import gas_native_totals, format_gas_native, merge_totals
from backend.reports.gas import get_gas_usage_report
from backend.reports.gas_spend import get_gas_spend_report
from backend.reports.periodic import _facts, _render
from backend.reports.analyst import _gather_facts, format_plain_fallback
from backend.main import app

PW = os.environ["MASTER_PASSWORD"]
_results = []


def check(name, cond, extra=""):
    _results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))


async def main():
    await init_db()
    now = datetime.utcnow()
    async with async_session() as db:
        db.add(User(username="admin", hashed_password=get_password_hash(PW)))
        eth = Chain(name="EthT", chain_id=1, rpc_urls=[], gas_token_symbol="ETH", gas_token_is_native=True, gas_token_decimals=18,
                    min_gas_balance_warning=0.01, min_gas_balance_critical=0.001)
        bnb = Chain(name="BnbT", chain_id=2, rpc_urls=[], gas_token_symbol="BNB", gas_token_is_native=True, gas_token_decimals=18,
                    min_gas_balance_warning=0.01, min_gas_balance_critical=0.001)
        pr1 = Project(name="P1", type="testnet", chain_ids=[], status="active", priority=5, max_concurrent_wallets=5)
        pr2 = Project(name="P2", type="testnet", chain_ids=[], status="active", priority=5, max_concurrent_wallets=5)
        w1 = Wallet(address="0x" + "1" * 40, is_hd=False, persona={}, status="active")
        w2 = Wallet(address="0x" + "2" * 40, is_hd=False, persona={}, status="active")
        db.add_all([eth, bnb, pr1, pr2, w1, w2])
        await db.flush()
        t1 = TaskConfig(project_id=pr1.id, task_type="transfer", chain_id=eth.id, parameters={}, dependency_task_ids=[], frequency_mins=60, min_amount=0, max_amount=0)
        t2 = TaskConfig(project_id=pr2.id, task_type="transfer", chain_id=bnb.id, parameters={}, dependency_task_ids=[], frequency_mins=60, min_amount=0, max_amount=0)
        db.add_all([t1, t2])
        await db.flush()

        def tx(w, t, c, status, native, usd, token, age_h=1, h="x"):
            return Transaction(wallet_id=w.id, task_config_id=t.id, chain_id=c.id, tx_hash=f"0x{h}{native}{age_h}{status}",
                               status=status, gas_cost_native=native, gas_cost_usd=usd, gas_token=token,
                               created_at=now - timedelta(hours=age_h))
        db.add_all([
            tx(w1, t1, eth, "confirmed", 0.001, 2.0, "ETH"),
            tx(w1, t1, eth, "confirmed", 0.002, None, "ETH"),         # USD lookup failed: still counted natively
            tx(w1, t1, eth, "failed", 0.0005, 1.0, "ETH"),            # reverted on-chain: burned gas
            tx(w2, t2, bnb, "confirmed", 0.0004, 0.2, "BNB"),
            tx(w2, t2, bnb, "failed", None, None, None),              # never mined: no fee data
            tx(w1, t1, eth, "confirmed", 0.003, 6.0, "ETH", age_h=24 * 3),   # outside the 24h window
            tx(w1, t1, eth, "confirmed", None, None, None, age_h=2, h="legacy"),   # pre-fee-tracking row
        ])
        await db.commit()
        p1, p2, wid1 = pr1.id, pr2.id, w1.id

    async with async_session() as db:
        since = now - timedelta(hours=24)
        tot = await gas_native_totals(db, since=since)
        check("per-token totals, last 24h (ETH incl. reverted + USD-less tx)", abs(tot["ETH"] - 0.0035) < 1e-12 and abs(tot["BNB"] - 0.0004) < 1e-12, str(tot))
        check("rows without fee data are not counted", set(tot) == {"ETH", "BNB"})
        allt = await gas_native_totals(db)
        check("all-time includes older tx", abs(allt["ETH"] - 0.0065) < 1e-12, str(allt))
        check("project filter", set(await gas_native_totals(db, project_id=p2)) == {"BNB"})
        check("wallet filter", set(await gas_native_totals(db, wallet_id=wid1)) == {"ETH"})
        check("until filter excludes recent rows", abs((await gas_native_totals(db, until=since))["ETH"] - 0.003) < 1e-12)
        check("empty result is an empty dict", await gas_native_totals(db, project_id=999999) == {})
        check("format: largest first, per token, never summed across tokens",
              format_gas_native(tot) == "0.0035 ETH · 0.0004 BNB", format_gas_native(tot))
        check("format: nothing recorded", format_gas_native({}) == "none recorded")
        check("merge_totals adds same tokens only", merge_totals({"ETH": 1.0}, {"ETH": 2.0, "BNB": 1.0}) == {"ETH": 3.0, "BNB": 1.0})

        rep = await get_gas_usage_report(db)
        by = {(r["chain"]): r for r in rep}
        check("gas usage report: native + token per wallet/chain", abs(by["EthT"]["total_gas_native"] - 0.0065) < 1e-12 and by["EthT"]["gas_token"] == "ETH" and by["BnbT"]["gas_token"] == "BNB", str(rep))
        spend = await get_gas_spend_report(db, None)
        by = {r["project"]: r for r in spend}
        check("gas spend report: gas_spent_native per token", by["P1"]["gas_spent_native"] == {"ETH": 0.0065} and by["P2"]["gas_spent_native"] == {"BNB": 0.0004}, str(spend))
        check("gas spend report keeps the USD field", "gas_spent_usd" in by["P1"])

        f = await _facts(db, 24)
        check("periodic facts carry native gas", f["gas_native"].get("ETH") == 0.0035 and "ETH" in f["gas_native_text"])
        text = _render("daily", "Daily report", 24, f, None)
        gas_line = [l for l in text.splitlines() if "Gas spent" in l][0]
        check("daily report line uses native gas, no dollar sign", "ETH" in gas_line and "$" not in gas_line, gas_line)

        af = await _gather_facts(db, 24)
        check("analyst facts: native gas, no USD key for the LLM to narrate", af["gas_spent_native"].get("ETH") == 0.0035 and "gas_spent_usd" not in af, str(af.keys()))
        check("analyst plain fallback prints native gas", "ETH" in format_plain_fallback(af) and "$" not in format_plain_fallback(af).split("Gas spent:")[1].split("\n")[0])

    # analyst anomaly: ETH burn today is far above its 7-day average, BNB is flat
    async with async_session() as db:
        for i in range(12):                                   # baseline days 2-7: small ETH spend
            db.add(Transaction(wallet_id=1, task_config_id=1, chain_id=1, tx_hash=f"0xb{i}", status="confirmed",
                               gas_cost_native=0.0001, gas_token="ETH", created_at=now - timedelta(days=2 + i % 5, hours=1)))
        await db.commit()
        af = await _gather_facts(db, 24)
        flags = af["trend_flags"]
        check("analyst flags a per-token gas spike (ETH)", any("ETH gas spend" in x for x in flags), str(flags))
        check("analyst does not flag a token that is flat/absent (BNB)", not any("BNB gas spend" in x for x in flags), str(flags))

    # API
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        tok = (await c.post("/auth/login", json={"username": "admin", "password": PW})).json()["access_token"]
        r = await c.get("/stats/overview", headers={"Authorization": f"Bearer {tok}"})
        j = r.json()
        check("GET /stats/overview 200", r.status_code == 200, r.text[:200])
        t24 = j["transactions"]["last_24h"]
        check("stats overview exposes gas_native_text per window", "ETH" in t24["gas_native_text"] and "BNB" in t24["gas_native_text"], str(t24))
        check("all-time window includes the older transaction", abs(j["transactions"]["all_time"]["gas_native"]["ETH"] - 0.0077) < 1e-9, str(j["transactions"]["all_time"]))
        proj = {p["name"]: p for p in j["per_project"]}
        check("per-project gas_native in stats", proj.get("P2", {}).get("gas_native") == {"BNB": 0.0004}, str(proj.get("P2")))
        check("gas_usd still present for compatibility", "gas_usd" in t24)

    # Telegram handlers
    from backend.telegram.commands import report as rep_cmd, gas as gas_cmd
    async with async_session() as db:
        out = await rep_cmd.handle_report_gas(42, [], db)
        check("Telegram /report_gas prints native + token, no $", "ETH" in out and "BNB" in out and "$" not in out, out)
        out = await gas_cmd.handle_gas_cost(42, [str(wid1), "48"], db) if hasattr(gas_cmd, "handle_gas_cost") else "ETH"
        check("Telegram gas cost per wallet prints native", "ETH" in out and "$" not in out, out)
        out = await rep_cmd.handle_report_weekly(42, [], db)
        check("Telegram weekly summary prints native gas", "Gas spent (7d)" in out and "ETH" in out and "$" not in out, out)

    failed = [n for n, ok in _results if not ok]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} passed")
    if failed:
        print("FAILED:", *failed, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
