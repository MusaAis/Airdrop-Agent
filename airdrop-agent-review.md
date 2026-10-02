# Airdrop-Agent — Code Review

**Scope:** full backend + frontend snapshot of `MusaAis/airdrop-agent` (read from the files provided; not executed, so items marked *verify* need a quick runtime check).
**Overall:** The architecture is solid (clean module split, deterministic-first AI design, good guardrails in `autonomy.py`, good SSRF check in `projects.py`). But several **core execution paths are broken**, and the auth layer has real holes. Fix the Critical section first — right now I don't think a task can complete a live transaction.

Severity: 🔴 Critical · 🟠 High · 🟡 Medium · 🔵 Low/Polish

---

## 🔴 Critical (execution engine / money path)

### C1. Gas check compares ETH to wei → every task skips as `low_gas`
`tasks/base.py::execute`
`get_gas_token_balance()` returns **ether** (`wei / 1e18`), but `estimate_gas()` returns **wei** (`gas * gas_price`). `gas_balance < required_gas` is then `0.1 < 2.5e13` → always true → every run returns `skipped / low_gas`. Same mismatch in `tasks/approval.py` and `tasks/simulation.py`.
**Fix (minimal):** convert the estimate once:
```python
# base.py, in execute()
required_gas = (gas_estimation / Decimal(10 ** self.chain.gas_token_decimals)) * Decimal("1.2")
```
(Do the same in `approval.py` and `simulation.py`.)

### C2. Counters/status changes on detached objects are never saved
`core/worker_pool.py::_execute_task`
`wallet`, `project`, `task_config` come from the queue items built inside `fill_queue`'s `async with async_session()` — that session is closed, so they're **detached**. `wallet.failure_count += 1`, `wallet.status = "cooldown"`, and `increment_failure(db, project)` mutate detached objects; the worker's `db.commit()` writes nothing for them. Result: the wallet cooldown, project circuit breaker, and the autonomy engine's `failure_count >= 2` trigger **never fire**.
**Fix:** at the top of `_execute_task`: `wallet = await db.merge(wallet); project = await db.merge(project)` (or reload by id).

### C3. Nonce starts at 0 and is never synced from chain
`core/nonce_manager.py::get_nonce` creates `WalletNonce(nonce=0)`. Nothing calls `sync_nonce_from_chain` before use, so any wallet with on-chain history gets `nonce too low` on its first tx. Drift after dropped/replaced txs is also never corrected.
**Fix:** in `lock_nonce`, after locking, return `max(record.nonce, await w3.eth.get_transaction_count(addr, "pending"))` and store it.

### C4. "Emergency stop"/confirm flow on Telegram can never execute
`telegram/bot.py`
- `dispatch_action()` re-stages any action in `_CONFIRM_REQUIRED` *every time it is called*. The `confirm` reply pops the pending action and calls `dispatch_action` again → hits the same `if action in _CONFIRM_REQUIRED` branch → asks for confirmation again. **`agent.kill`, `wallet.blacklist`, `chain.disable`, `nonce.release_all` can never run via Telegram.**
- `/agent_kill` isn't registered as a slash command at all.
- Handlers like `handle_wallet_pause`, `handle_task_pause`, `handle_project_disable/pause`, `handle_tx_cancel/speedup`, `handle_chain_disable` return "Reply 'confirm'" when `confirmation is None`, but `make_cmd` never passes `confirmation` and never stages a pending action — so those slash commands are also stuck.
**Fix:** add a `skip_confirm` param: `dispatch_action(..., confirmed=False)`; the `confirm` handler calls it with `confirmed=True`; in `make_cmd` stage a pending action when a handler returns a confirm prompt (or pass `confirmation="confirm"` after staging). Register `agent_kill`.

### C5. Dry-run still sends real approval transactions
`tasks/base.py::execute`
The dry-run gate is checked at step 16, but `handle_approval()` (a real `approve` broadcast) runs before it. Dry-run mode therefore spends gas and sets on-chain allowances.
**Fix:** `if is_dry_run() and needs_approval:` log + return `simulated` before calling `handle_approval()`.

### C6. Auto-started agent loop can't be stopped; `/agent/start` can double-start
`main.py` does `asyncio.create_task(agent_loop())` without setting `agent.agent_task`, so `stop_agent()`/`/agent/stop`/kill's `stop_agent()` cancel nothing. Conversely `POST /agent/start` doesn't check `worker_pool.running` and spawns a **second** loop + second set of slot workers.
**Fix:** use `start_agent()` in `main.py`; guard `start_agent()` with `if agent_task and not agent_task.done(): return agent_task`.

### C7. Auth: refresh/device tokens are valid access tokens; refresh accepts access tokens
`security/auth.py`, `routes/auth.py`, `security/device_trust.py`
All JWTs share one key and `verify_token` never checks a `type` claim. So (a) a 7-day refresh token and the 30-day device-trust cookie JWT both work as Bearer access tokens, and (b) `/auth/refresh` accepts a plain access token, letting a stolen 30-min token be renewed forever. `/refresh` also takes the token as a **query param** (ends up in logs) and never checks the user still exists.
**Fix:** add `"type": "access"|"refresh"` to payloads; `decode_token(token, expected_type)`; take the refresh token in the body/cookie.

### C8. Empty `MASTER_PASSWORD` creates an admin with an empty password
`main.py` hashes `MASTER_PASSWORD` for the `admin` user, and `config.py` defaults it to `""`. The same value is also the encryption password for all private keys and the seed. `SECRET_KEY` also defaults to a known string.
**Fix:** refuse to start if `MASTER_PASSWORD` is empty/short or `SECRET_KEY == "please-change-me-in-production"`. Better: use a **separate** key-encryption secret from the login password.

---

## 🟠 High

### H1. 2FA can be silently replaced with only a JWT
`POST /auth/totp/setup` sets `totp_enabled=False` and a new secret with no TOTP/password check. Anyone with a (stolen) access token can call setup → verify-setup and own the second factor. **Fix:** if `totp_enabled`, require the current code (or password) before `/setup`.

### H2. Stats/gas/log data is mostly empty
- `Transaction.gas_cost_usd`/`gas_token` are **never set** anywhere → gas reports, stats overview, daily summary, analyst trend flags, `achieve_volume`, and the `volume` criterion all read 0.
- `Log` rows are only written in the dry-run path, so the live WebSocket log, `send_daily_summary()` and log archival see nothing for real txs.
- `Transaction.error_message` is never set on failure.
**Fix:** after a receipt, compute `gas_used * effective_gas_price / 1e18 * price` and write it; add a `Log` row on every outcome.

### H3. Live log page shows heartbeat junk
`ws.py` sends `{type, data}` envelopes (incl. a heartbeat every 2s). `Logs.jsx` does `setLogs(prev => [JSON.parse(e.data), ...])` — it inserts envelopes as rows (all columns undefined) and the 200-row cap fills with heartbeats. **Fix:** `const m = JSON.parse(e.data); if (m.type === 'log') ...`. Also `Dashboard.jsx`/`Logs.jsx` default WS port is `8000` but the server runs on `8002`. Also the WS replays from `Log.id > 0` on every connect.

### H4. Anti-Sybil "human behaviour" isn't actually applied
- `frequency_mins` and persona sleep times (`get_sleep_seconds`) are never used by the queue → a wallet burns its whole daily target back-to-back on 30s cycles.
- `delay_seconds` (start offset) is only `await asyncio.sleep`'d **after** `enqueue()` inside `fill_queue`, which just blocks the fill loop up to `30 × N` s and staggers nothing.
- `last_selected_at` is never updated, so the "least-recently-used" sort always picks the same wallets first.
- `randomize_amount()` ignores `WalletSettings.amount_*_override`/`amount_vary_daily` despite the comment.
**Fix:** track `next_run_at` per wallet+task (the `TaskSchedule` table exists and is unused) and honor it in `_get_project_candidates`.

### H5. Restart → mass failures
After a restart the master seed isn't loaded (`/agent_unlock` required), but the agent starts immediately. HD wallets then fail at signing (`No master seed set`), classified `unknown` → wallets to cooldown, projects circuit-broken. **Fix:** in `fill_queue`, skip HD wallets (or return early) while `get_master_seed()` is None, and alert once.

### H6. Private-key export API
`POST /agent/wallets/{id}/private-key` returns raw keys given a JWT + the master password (which is the same as the login password). One credential compromise = all keys. **Fix:** remove it, or require TOTP + separate secret + rate-limit; never return keys over the wire for HD wallets (the seed is recoverable offline).

### H7. Webhooks = SSRF + broken
`routes/webhooks.py`: server POSTs to any user-supplied URL (no private-IP check — reuse `_assert_public_http_url`); `dispatch_event` declares `Depends(verify_token)` (will fail when called normally); IDs are list indexes so unregister shifts every ID and negative IDs pop from the end; errors swallowed. It's unused — **delete it or fix it**.

### H8. Wallet import fails with `0x` keys
`import_private_key` does `bytes.fromhex(private_key)` — the UI placeholder says `0x…` → `ValueError` → 500. Strip `0x`. Also validate length (64 hex).

### H9. Bad CoinGecko ids → no USD values
`balance.py` uses `chain.gas_token_symbol.lower()` (`"eth"`) as the CoinGecko id; CoinGecko needs `"ethereum"`. Add a `coingecko_id` column on `Chain` (tokens already have one). Also `check_erc20_balance_raw` passes DB addresses un-checksummed — web3 v7 raises on that; wrap in `to_checksum_address`.

---

## 🟡 Medium

- **In-place JSON mutation isn't persisted.** `handle_wallet_tag` does `tags = wallet.tags or []; tags.append(x); wallet.tags = tags` — same object, so SQLAlchemy sees no change. Use `wallet.tags = [*tags, x]` (or `MutableList`/`flag_modified`). Same pattern in the (unregistered) chain RPC handlers.
- **`Wallet.tags.contains(tag)`** on a generic JSON column isn't valid on SQLite (tag filter / `/wallet_group` likely errors). Use `func.json_each` or a tags table.
- **`/wallets/generate` default `start_index=0`** bypasses the "max hd_index + 1" logic in `create_hd_wallets` → duplicate-address 500s when the client omits it. Make it `Optional[int] = None`.
- **Signing blocks the event loop.** Every `sign_transaction` runs PBKDF2 (600k iters) and/or re-derives from mnemonic (`mnemo.to_seed` + `from_mnemonic`) synchronously. Cache decrypted keys in memory for the session, or `run_in_executor`.
- **Stuck-tx handler vs. `execute`.** After a speed-up, `monitor_tx` returns `None`, so `execute()` marks the (replaced) tx `failed` and counts a wallet failure; its own stale `tx_record` also overwrites the handler's "replaced" status (different sessions). The replacement hash is never monitored (`monitor_pending_transactions` only sees `pending`).
- **Task timeout (480s) can be shorter than the sum of its steps** (approval delay 30–90s + approval monitor 180s + main monitor 300s). `wait_for` cancels mid-flight, leaving nonce state dirty.
- **Eligibility has two inconsistent implementations.** `reports/eligibility.py` marks a criterion "met" if the wallet has *any* tx; `projects/eligibility.py` is the real one but uses `gas_cost_usd` as a volume proxy (always 0), a nonsense governance check, and treats `uncertain` social criteria as **met** (inverted). `SocialTask` tracking exists but isn't used. Consider showing "unverifiable" rather than a fake %.
- **Faucet cooldown counts failed requests.** `_do_request` blocks for `cooldown_hours` after *any* previous request, including `failed`. A transient faucet error then locks a wallet out for 24h. Filter `status == "success"` (as `cooldown_tracker.py` already does). Also "success" = HTTP 200, not "funds arrived" — verify with a balance check.
- **Brute-force uses `request.client.host`**, which is the tunnel/proxy IP behind Cloudflare, while the IP middleware uses `cf-connecting-ip`. All clients may share one lockout bucket (self-DoS). Also DB failures aren't cleared on success, so 5 old failures still lock a user after a good login. In-memory dict never pruned.
- **`/auth/login` timing** reveals whether a username exists (no hash check when user missing).
- **DB layer:** SQLite with many concurrent writers needs `connect_args={"timeout": 30}` / `busy_timeout`; `init_db` PRAGMAs break the documented Postgres path. Alembic `target_metadata = None`, so autogenerate is dead; new columns on existing tables (Phase 4) aren't applied by `create_all`. Set up Alembic properly.
- **`rpc_pool`:** cached web3 isn't invalidated when RPC URLs change; each `get_web3()` does an extra `block_number` call; `rpc_rate_limit_per_sec` / `get_rate_limiter` are never used; no request timeout on the provider.
- **Queue fill is O(wallets × tasks) DB queries every 30s**, plus commits in `get_or_create_daily_target`. Fine at 10 wallets, painful at 200. Batch with joins.
- **Sybil report writes on GET** (`get_sybil_report` recomputes correlations and commits) with O(n²·m²) loops; scores never decay.
- **`handle_system_status`** reads `s.get("emergency_stop")` which `get_server_status()` doesn't return → always shows "Normal". Add the key.
- **`config.set` arg order:** NL dispatch passes `[wallet_id, key, value]`; handler expects `[setting, wallet_id, values…]`. `_validate_config_change` (AI check promised in the plan) is never called.
- **`task.trigger` via NL** passes `"random"` → `int("random")` crash; also no emergency-stop / active-wallet check (the `/ops` route has both).
- **Autonomy `wallet_pause` rarely triggers.** It needs `failure_count >= 2`, but `low_gas` outcomes are now *skips* (don't increment failure_count) and C2 means counts aren't persisted anyway. Trigger on the cluster evidence instead.
- **AI risk review has no evidence.** `project.approve` feeds the model only name/URLs/criteria, but the prompt asks it to check GitHub commits, Discord size, VC backing, testnet explorers. It will invent "evidence". Either fetch real data or reword the prompt so it can only say "not provided".
- **Gemini model list** contains retired models (`1.5-*`); on a non-404 error `ask_gemini` raises without trying the next key/model.
- **CORS** allows only `airdrop-agent-wine.vercel.app`, while PLAN.md lists `airdrop-agent-musaais.vercel.app` as the production frontend — verify.

---

## 🔵 Low / polish

- `classify_error_text`: `"429" in t` matches any text containing those digits (amounts, hashes) → false `rpc_error`.
- `ErrorBoundary` "Try again" re-renders the same crashed tree; reset with a `key`.
- `vite.config.js` has a duplicate `/autonomy` key, no `/claims` proxy.
- `Login.jsx` stores the JWT in `localStorage` while `App.jsx` says "React state only"; XSS-readable. Prefer httpOnly refresh cookie + in-memory access token.
- Dead/stale code to delete: `faucet/handlers/*`, `faucet/scheduler.py` (duplicates scheduler job), `tasks/simulation.py`, `wallet/warmup.py` (`_run_aging_simple` references undefined `w3`; `handle_wallet_warmup` passes args in the wrong order and shares the request's DB session with a background task), `telegram/commands/gas.py|competitor.py|task.py` extras, `help.py.bak`, `handle_ai_validate` (imports a non-existent `validate_project`), `alembic` stubs, `bip32utils`, `backend/ai/validators.py`.
- `requirements.txt` is unpinned; add a lock file (`pip-compile`), `eth-account`/`hexbytes` explicit pins.
- `@app.on_event("startup")` is deprecated → use `lifespan`.
- Expose `health_score`/`sybil_risk_score` in `WalletResponse` (already noted in PLAN).
- Telegram `/agent_unlock <password>` leaves the password in chat history — auto-delete the message after reading.
- No tests/CI. At minimum add unit tests for: gas unit conversion, nonce lock/sync, `compare_outputs`, `classify_error_text`, `_do_change` bounds, `_project_is_dispatchable`.

### Library-compat risks (*verify*)
- `signed.rawTransaction` → newer `eth-account` renamed it to `raw_transaction`.
- `tx_hash.hex()` with `hexbytes>=1.0` returns **no `0x` prefix**; those strings are then stored and passed back to `get_transaction_receipt` / compared. Use `w3.to_hex(tx_hash)`.

### Ops / deployment
- Bind uvicorn to `127.0.0.1` behind the tunnel and/or firewall port 8002; the IP-whitelist middleware is commented out (PLAN already flags it), and `/docs` + `/openapi.json` are public.
- Harden the systemd unit (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=` for the DB, `PrivateTmp=yes`) and `chmod 600 .env`.
- Persist emergency-stop and dry-run (already in "Known, not built") — until then a restart can silently go live.
- Add a one-click **Kill** button on the dashboard (only `/agent/kill` API exists) since the Telegram path is broken (C4).

---

## Suggested fix order
1. C1 (gas units) → C2 (merge detached objects) → C3 (nonce sync) → C5 (dry-run approvals) — the engine can't work without these.
2. C4/C6 (kill + stop controls) — safety controls must actually work.
3. C7/C8/H1/H6 — auth & secrets.
4. H2/H3 — logging/gas data so reports and the dashboard show reality.
5. H4/H5 — behaviour realism and restart safety.
6. Medium list, then cleanup of dead code and tests.

Happy to turn any of these into minimal `sed`/patch snippets per file.
