"""
Tests for review items C7, C8, H1, H2, H6, H7, H8, H9 and the SQLite column migration.

Run from the repo root:   python3 -m backend.test_security_fixes
No network, no chain, no Telegram: uses a throwaway SQLite file and an in-process ASGI client.
"""
import asyncio, logging, os, subprocess, sys, tempfile, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/t.db",
    "MASTER_PASSWORD": "correct-horse-battery-staple",
    "SECRET_KEY": "k" * 48,
    "TELEGRAM_ALLOWED_USER_IDS": '["42"]',
})
logging.disable(logging.CRITICAL)

import httpx, pyotp
from jose import jwt
from sqlalchemy import select, text
from backend.config import SECRET_KEY, ALGORITHM
from backend.database import init_db, async_session, engine
from backend.models import User, Chain, Transaction
from backend.security.auth import (
    get_password_hash, create_access_token, create_refresh_token, verify_token_str,
    decode_token, TOKEN_TYPE_ACCESS, TOKEN_TYPE_REFRESH,
)
from backend.security.device_trust import create_device_trust_token
from backend.security.startup_checks import check_secrets, enforce_startup_secrets
from backend.main import app

PW = os.environ["MASTER_PASSWORD"]
_results = []


def check(name, cond, extra=""):
    _results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


async def make_client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://t")


async def reset_user():
    async with async_session() as db:
        await db.execute(text("DELETE FROM users"))
        db.add(User(username="admin", hashed_password=get_password_hash(PW)))
        await db.commit()


# ------------------------------------------------------------------ C7
async def test_c7(c):
    await reset_user()
    r = await c.post("/auth/login", json={"username": "admin", "password": PW})
    check("C7 login returns tokens", r.status_code == 200, r.text)
    access, refresh = r.json()["access_token"], r.json()["refresh_token"]

    check("C7 access token works as Bearer", (await c.get("/chains/", headers=hdr(access))).status_code == 200)
    check("C7 refresh token REJECTED as Bearer", (await c.get("/chains/", headers=hdr(refresh))).status_code == 401)
    device = create_device_trust_token("admin")
    check("C7 device-trust token REJECTED as Bearer", (await c.get("/chains/", headers=hdr(device))).status_code == 401)
    legacy = jwt.encode({"sub": "admin", "exp": time.time() + 600}, SECRET_KEY, algorithm=ALGORITHM)
    check("C7 old untyped token REJECTED", (await c.get("/chains/", headers=hdr(legacy))).status_code == 401)

    check("C7 access token REJECTED by /auth/refresh",
          (await c.post("/auth/refresh", json={"refresh_token": access})).status_code == 401)
    check("C7 device-trust token REJECTED by /auth/refresh",
          (await c.post("/auth/refresh", json={"refresh_token": device})).status_code == 401)
    check("C7 refresh token in query string no longer accepted",
          (await c.post(f"/auth/refresh?refresh_token={refresh}")).status_code == 422)
    r = await c.post("/auth/refresh", json={"refresh_token": refresh})
    check("C7 valid refresh token -> new access token that works",
          r.status_code == 200 and (await c.get("/chains/", headers=hdr(r.json()["access_token"]))).status_code == 200)

    async with async_session() as db:
        await db.execute(text("DELETE FROM users"))
        await db.commit()
    check("C7 refresh fails once the user is gone",
          (await c.post("/auth/refresh", json={"refresh_token": refresh})).status_code == 401)

    ok = True
    try:
        verify_token_str(refresh)
        ok = False
    except Exception:
        pass
    check("C7 websocket verifier rejects refresh token", ok)
    check("C7 decode_token requires a matching type",
          decode_token(access, TOKEN_TYPE_REFRESH) is None and decode_token(refresh, TOKEN_TYPE_ACCESS) is None
          and decode_token(access, TOKEN_TYPE_ACCESS)["sub"] == "admin")


# ------------------------------------------------------------------ C8
async def test_c8():
    e, w = check_secrets("k" * 48, PW)
    check("C8 good secrets -> no errors", not e and not w, f"{e} {w}")
    e, _ = check_secrets("k" * 48, "")
    check("C8 empty MASTER_PASSWORD is an error", len(e) == 1)
    e, _ = check_secrets("please-change-me-in-production", PW)
    check("C8 default SECRET_KEY is an error", len(e) == 1)
    e, _ = check_secrets("short", PW)
    check("C8 short SECRET_KEY is an error", len(e) == 1)
    e, _ = check_secrets("k" * 48, "your-strong-master-password-here")
    check("C8 .env.example placeholder password is an error", len(e) == 1)
    e, _ = check_secrets("change-me-to-a-random-64-char-string", PW)
    check(".env.example placeholder SECRET_KEY is an error", len(e) == 1)
    e, w = check_secrets("k" * 48, "tenchars!!")
    check("C8 10-char password: allowed but warned", not e and len(w) == 1)
    e, _ = check_secrets("k" * 48, "short")
    check("C8 <8-char password is an error", len(e) == 1)

    try:
        enforce_startup_secrets("k" * 48, "")
        raised = False
    except SystemExit:
        raised = True
    check("C8 enforce raises SystemExit on bad secrets", raised)
    try:
        enforce_startup_secrets("k" * 48, "", allow_insecure=True)
        ok = True
    except SystemExit:
        ok = False
    check("C8 ALLOW_INSECURE_SECRETS escape hatch works", ok)

    # the real app startup, in a fresh process with an empty MASTER_PASSWORD
    env = {**os.environ, "MASTER_PASSWORD": "", "DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/boot.db"}
    p = subprocess.run(
        [sys.executable, "-c", "import asyncio; from backend.main import startup; asyncio.run(startup())"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    check("C8 app startup exits non-zero with empty MASTER_PASSWORD",
          p.returncode != 0 and "Refusing to start" in (p.stderr + p.stdout), (p.stderr or p.stdout)[-200:])
    check("C8 refused start never touched the database (no admin created)",
          not os.path.exists(f"{_tmp}/boot.db"))


# ------------------------------------------------------------------ H1
async def test_h1(c):
    await reset_user()
    r = await c.post("/auth/login", json={"username": "admin", "password": PW})
    tok = r.json()["access_token"]

    check("H1 setup with no password -> 422", (await c.post("/auth/totp/setup", json={}, headers=hdr(tok))).status_code == 422)
    r = await c.post("/auth/totp/setup", json={"password": "wrong"}, headers=hdr(tok))
    check("H1 setup with wrong password -> 401", r.status_code == 401)
    r = await c.post("/auth/totp/setup", json={"password": PW}, headers=hdr(tok))
    secret = r.json().get("secret")
    check("H1 setup with password returns a secret", r.status_code == 200 and secret)

    async with async_session() as db:
        u = (await db.execute(select(User))).scalar_one()
        check("H1 secret not stored before verification", u.totp_secret is None and not u.totp_enabled)

    check("H1 verify-setup rejects a wrong code",
          (await c.post("/auth/totp/verify-setup", json={"totp_code": "000000"}, headers=hdr(tok))).status_code == 401)
    r = await c.post("/auth/totp/verify-setup", json={"totp_code": pyotp.TOTP(secret).now()}, headers=hdr(tok))
    check("H1 verify-setup with real code enables 2FA", r.status_code == 200 and r.json()["totp_enabled"])

    # login now needs TOTP
    r = await c.post("/auth/login", json={"username": "admin", "password": PW})
    check("H1 login requires totp after enabling", r.status_code == 401 and r.json()["detail"] == "totp_required")

    # 2FA already on: a bearer token alone must NOT replace it
    r = await c.post("/auth/totp/setup", json={"password": PW}, headers=hdr(tok))
    check("H1 replacing 2FA without current code -> 401", r.status_code == 401)
    async with async_session() as db:
        u = (await db.execute(select(User))).scalar_one()
        check("H1 2FA still enabled with old secret after failed replace", u.totp_enabled and u.totp_secret == secret)

    r = await c.post("/auth/totp/setup", json={"password": PW, "totp_code": pyotp.TOTP(secret).now()}, headers=hdr(tok))
    new_secret = r.json().get("secret")
    check("H1 replacing 2FA with password + current code gives a new secret", r.status_code == 200 and new_secret != secret)
    async with async_session() as db:
        u = (await db.execute(select(User))).scalar_one()
        check("H1 old secret + 2FA stay active until the new one is verified", u.totp_enabled and u.totp_secret == secret)
    r = await c.post("/auth/login", json={"username": "admin", "password": PW, "totp_code": pyotp.TOTP(secret).now()})
    check("H1 login still works with the OLD authenticator while replacement is pending", r.status_code == 200)

    r = await c.post("/auth/totp/disable", json={"password": "wrong", "totp_code": pyotp.TOTP(secret).now()}, headers=hdr(tok))
    check("H1 disable needs the right password", r.status_code == 401)
    r = await c.post("/auth/totp/disable", json={"password": PW, "totp_code": pyotp.TOTP(secret).now()}, headers=hdr(tok))
    check("H1 disable with password + code works", r.status_code == 200 and not r.json()["totp_enabled"])

    # failure limiter
    import backend.api.routes.auth as auth_routes
    auth_routes._sensitive_fails.clear()
    codes = []
    for _ in range(7):
        codes.append((await c.post("/auth/totp/setup", json={"password": "bad"}, headers=hdr(tok))).status_code)
    check("H1 repeated failures are rate-limited (429 after 5)", codes[:5] == [401] * 5 and codes[5] == 429, str(codes))
    auth_routes._sensitive_fails.clear()


# ------------------------------------------------------------------ H6 / H7
async def test_h6_h7(c):
    await reset_user()
    tok = (await c.post("/auth/login", json={"username": "admin", "password": PW})).json()["access_token"]
    r = await c.post("/agent/wallets/1/private-key", json={"master_password": PW}, headers=hdr(tok))
    check("H6 private-key export endpoint is gone", r.status_code in (404, 405), str(r.status_code))
    r = await c.post("/webhooks/register?url=http://169.254.169.254/&events=x", headers=hdr(tok))
    check("H7 webhook registry (SSRF) is gone", r.status_code == 404, str(r.status_code))
    paths = {getattr(rt, "path", "") for rt in app.routes}
    check("H6/H7 neither route is mounted", "/webhooks/register" not in paths and "/agent/wallets/{wallet_id}/private-key" not in paths)


# ------------------------------------------------------------------ H8
async def test_h8(c):
    from backend.wallet.manager import normalize_private_key
    k = "1" * 64
    check("H8 bare key accepted", normalize_private_key(k) == k)
    check("H8 0x key accepted", normalize_private_key("0x" + k) == k)
    check("H8 whitespace + 0X + uppercase normalised", normalize_private_key(f"  0X{'AB' * 32}\n") == "ab" * 32)
    for bad in ["", "0x", "0x" + "1" * 63, "1" * 65, "z" * 64]:
        try:
            normalize_private_key(bad)
            ok = False
        except ValueError as e:
            ok = len(bad) < 8 or bad not in str(e)       # error text must not echo a real-looking key
        check(f"H8 rejects invalid key {bad[:8]!r}...", ok)

    await reset_user()
    tok = (await c.post("/auth/login", json={"username": "admin", "password": PW})).json()["access_token"]
    pk = "0x" + "11" * 32
    r = await c.post("/wallets/import", json={"private_key": pk, "name": "w"}, headers=hdr(tok))
    check("H8 import with 0x key -> 200 (was 500)", r.status_code == 200, r.text)
    r2 = await c.post("/wallets/import", json={"private_key": pk[2:]}, headers=hdr(tok))
    check("H8 importing the same key again -> 409", r2.status_code == 409, r2.text)
    r3 = await c.post("/wallets/import", json={"private_key": "0xnothex"}, headers=hdr(tok))
    check("H8 garbage key -> 400", r3.status_code == 400, r3.text)

    # the stored key must decrypt back to the same key
    from backend.models import Wallet
    from backend.wallet.crypto import decrypt_private_key
    async with async_session() as db:
        w = (await db.execute(select(Wallet).where(Wallet.id == r.json()["id"]))).scalar_one()
        check("H8 stored encrypted key round-trips to the normalised key",
              decrypt_private_key(w.encrypted_private_key, PW) == "11" * 32)


# ------------------------------------------------------------------ H9
async def test_h9():
    from backend.wallet.balance import chain_coingecko_id, check_erc20_balance_raw
    mk = lambda sym, cg=None: SimpleNamespace(gas_token_symbol=sym, coingecko_id=cg)
    check("H9 ETH -> ethereum", chain_coingecko_id(mk("ETH")) == "ethereum")
    check("H9 BNB -> binancecoin", chain_coingecko_id(mk("bnb")) == "binancecoin")
    check("H9 explicit coingecko_id wins", chain_coingecko_id(mk("ETH", " Custom-Id ")) == "custom-id")
    check("H9 unknown symbol falls back to lowercase symbol", chain_coingecko_id(mk("ZZZ")) == "zzz")

    seen = {}

    class FakeFn:
        def __init__(self, addr): self.addr = addr
        async def call(self):
            seen["owner"] = self.addr
            return 5

    class FakeContract:
        def __init__(self, address): seen["contract"] = address
        class functions:
            @staticmethod
            def balanceOf(a): return FakeFn(a)

    w3 = SimpleNamespace(eth=SimpleNamespace(contract=lambda address, abi: FakeContract(address)))
    low_c, low_o = "0x" + "ab" * 20, "0x" + "cd" * 20
    out = await check_erc20_balance_raw(w3, low_c, low_o)
    from web3 import Web3
    check("H9 ERC20 call uses checksummed addresses",
          out == 5 and seen["contract"] == Web3.to_checksum_address(low_c) and seen["owner"] == Web3.to_checksum_address(low_o))


# ------------------------------------------------------------------ H2
async def test_h2():
    import backend.tasks.base as base
    base.get_usd_price = AsyncMock(return_value=2000.0)
    chain = SimpleNamespace(gas_token_symbol="ETH", coingecko_id=None, gas_token_is_native=True, gas_token_decimals=18)
    me = SimpleNamespace(chain=chain)
    rec = SimpleNamespace(gas_price=1_000_000_000, tx_hash="0xabc", gas_used=None, gas_token=None,
                          gas_cost_native=None, gas_cost_usd=None)
    receipt = {"gasUsed": 21000, "effectiveGasPrice": 2_000_000_000}

    class R(dict):
        gasUsed = 21000
    await base.BaseTask._record_fee(me, rec, R(receipt))
    native = 21000 * 2_000_000_000 / 1e18
    check("H2 gas_used / gas_token recorded", rec.gas_used == 21000 and rec.gas_token == "ETH")
    check("H2 native fee = gasUsed x effectiveGasPrice", abs(rec.gas_cost_native - native) < 1e-15, str(rec.gas_cost_native))
    check("H2 USD estimate = native x price", abs(rec.gas_cost_usd - native * 2000.0) < 1e-9, str(rec.gas_cost_usd))
    base.get_usd_price = AsyncMock(side_effect=RuntimeError("coingecko down"))
    rec2 = SimpleNamespace(gas_price=1_000_000_000, tx_hash="0xdef", gas_used=None, gas_token=None,
                           gas_cost_native=None, gas_cost_usd=None)
    await base.BaseTask._record_fee(me, rec2, R({"gasUsed": 21000}))
    check("H2 price outage keeps the native fee, leaves USD empty, never raises",
          rec2.gas_cost_native is not None and rec2.gas_cost_usd is None)
    check("H2 falls back to the submitted gas price when the receipt has none",
          abs(rec2.gas_cost_native - 21000 * 1_000_000_000 / 1e18) < 1e-15)


# ------------------------------------------------------------------ migration
async def test_migration():
    await init_db()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE chains DROP COLUMN coingecko_id"))
        await conn.execute(text("ALTER TABLE transactions DROP COLUMN gas_cost_native"))
    await init_db()
    await init_db()   # idempotent
    async with engine.begin() as conn:
        chain_cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(chains)"))).fetchall()]
        tx_cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(transactions)"))).fetchall()]
    check("MIGRATION missing columns are re-added, twice is harmless",
          "coingecko_id" in chain_cols and "gas_cost_native" in tx_cols)
    async with async_session() as db:
        db.add(Chain(name="C", chain_id=99, rpc_urls=[], gas_token_symbol="ETH", gas_token_is_native=True,
                     gas_token_decimals=18, min_gas_balance_warning=0.01, min_gas_balance_critical=0.001,
                     coingecko_id="ethereum"))
        await db.commit()
        c = (await db.execute(select(Chain).where(Chain.chain_id == 99))).scalar_one()
        check("MIGRATION new column is usable", c.coingecko_id == "ethereum")


async def main():
    await init_db()
    c = await make_client()
    try:
        await test_c7(c)
        await test_c8()
        await test_h1(c)
        await test_h6_h7(c)
        await test_h8(c)
        await test_h9()
        await test_h2()
        await test_migration()
    finally:
        await c.aclose()
    failed = [n for n, ok in _results if not ok]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} passed")
    if failed:
        print("FAILED:", *failed, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
