# API and Telegram reference

All HTTP routes except those marked public require `Authorization: Bearer <access token>`. Refresh and device-trust tokens are rejected there.

## REST API (130 endpoints)
| Prefix | Purpose |
|---|---|
| `/auth` | `login` (public), `refresh` (public, JSON body), `totp/setup`, `totp/verify-setup`, `totp/disable` |
| `/agent` | `health` (public), `status`, `start`, `stop`, `kill`, `workers`, `queue`, `set-seed`, `unlock`, alerts list/resolve/snooze |
| `/wallets` | list, balances, generate, import, status, settings, gas-wallet toggle |
| `/chains` | CRUD (incl. `coingecko_id`), test RPC, token registry |
| `/projects` | CRUD (delete = archive), restore, stop, eligibility declare/clear, tasks, per-wallet eligibility, criteria draft/accept |
| `/faucets` | CRUD, tokens, request, request-all, per-wallet status |
| `/proxies` | CRUD, assign, activate, test |
| `/ai` | validations list/detail/resolve, validate |
| `/autonomy` | status, pause, resume, actions, approve, undo |
| `/reports` | eligibility, gas (per wallet/chain: `total_gas_native` + `gas_token`), gas-spend (`gas_spent_native` per token), daily-progress, sybil, activity, server, summary, performance/*, export/{table} |
| `/stats` | `overview`: transaction windows (`last_24h`, `last_7d`, `all_time`) and `per_project` rows carry `gas_native` (per-token dict), `gas_native_text` and the legacy `gas_usd` estimate |
| `/claims` | `scan` (read-only, cached 10 min; `?refresh=true`) |
| `/ops` | project details/contracts/criteria/trigger-all/reset-circuit, task edit/trigger, wallet tags/recover/nonces/settings/persona re-roll, `transactions`, chain gas status, `system` (dry-run (persisted), emergency clear, archive logs, agent start/stop, seed unlock), `claims/*` |
| `/ws/logs` | WebSocket, `?token=<access jwt>`; closes with code 4001 otherwise. Events `log`, `status`, `heartbeat` |
| `/ws/recent-logs` | history of latest logs |

Removed: `POST /agent/wallets/{id}/private-key` (key export) and the `/webhooks` router (unused, SSRF risk).

Interactive docs: `/docs` and `/openapi.json` (public; the IP whitelist is intentionally off).

### Auth request shapes
```
POST /auth/login          {"username", "password", "totp_code"?}   -> access_token, refresh_token
POST /auth/refresh        {"refresh_token"}                        -> access_token
POST /auth/totp/setup     {"password", "totp_code"?}               -> secret, qr_code_base64
                          (totp_code is required when 2FA is already enabled)
POST /auth/totp/verify-setup {"totp_code"}                         -> enables 2FA with the pending secret
POST /auth/totp/disable   {"password", "totp_code"}                -> disables 2FA
```
Failures on the three `totp` routes are limited to 5 per 15 minutes per user (then 429).

### Enabling 2FA
```bash
TOKEN=...   # access_token from /auth/login
curl -s -X POST https://api.example.com/auth/totp/setup \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"password": "<MASTER_PASSWORD>"}'
# scan the QR / enter the secret in your authenticator, then:
curl -s -X POST https://api.example.com/auth/totp/verify-setup \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"totp_code": "123456"}'
```
Complete `verify-setup` within 10 minutes; until then any existing 2FA stays active.

### Wallet import
`POST /wallets/import {"private_key", "name"?, "tags"?}`: key may be bare or `0x`-prefixed hex (64 chars). 400 for malformed keys, 409 if the address already exists.

## Telegram commands
Registered command table (73) plus `start`, `help`, `commands`, `agent_unlock`, `agent_kill`, `report_summary`, and group commands `group_setup`, `group_status`, `report_now [daily|weekly|monthly|ai]`.

| Group | Commands |
|---|---|
| Wallet | `wallet_create` `wallet_list` `wallet_status` `wallet_balance` `wallet_pause` `wallet_resume` `wallet_blacklist` `wallet_archive` `wallet_tag` `wallet_group` `wallet_fund` `wallet_health` `wallet_sybil` `wallet_top` `wallet_failing` `wallet_set_gas` |
| Chain | `chain_list` `chain_add` `chain_enable` `chain_disable` `chain_status` `chain_gas` `chain_tokens` `chain_add_token` |
| Task | `task_list` `task_status` `task_enable` `task_pause` `task_trigger` |
| Project | `project_list` `project_add` `project_status` `project_enable` `project_disable` `project_pause` `project_resume` `project_approve` `project_reject` `project_gap` `project_reset_circuit` |
| Agent | `agent_status` `agent_start` `agent_stop` `agent_pause_all` `agent_resume_all` `agent_unlock` `agent_kill` |
| Faucet / Claim | `faucet_request` `faucet_bulk` `claim_check` `claim_eligible` `claim_trigger` (prints instructions only) `claim_pending` |
| Reports | `report_eligibility` `report_daily_progress` `report_gas` `report_server` `report_summary` `report_now` |
| Config | `config_show` `config_set` |
| AI | `ai_status` `ai_pending` `ai_approve` `ai_reject` `ai_autonomy_off` `ai_autonomy_on` |
| Ops | `nonce_release_all` `tx_stuck` `tx_speedup` `tx_cancel` `gas_price` `gas_refill` `alert_list` `alert_resolve_all` `system_status` `system_version` |

Commands marked destructive stage a confirmation: reply `confirm` within 60 s, or `cancel`.
Known quirks: `config_set` via natural language passes arguments in a different order than the handler expects; `task_trigger` via natural language with "random" crashes; `system_status` always shows emergency stop as normal.
