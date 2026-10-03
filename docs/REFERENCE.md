# API and Telegram reference

All HTTP routes except those marked public require `Authorization: Bearer <access token>`.

## REST API (133 endpoints)
| Prefix | Purpose |
|---|---|
| `/auth` | `login`, `refresh`, `totp/setup`, `totp/verify-setup`, `totp/disable` |
| `/agent` | `health` (public), `status`, `start`, `stop`, `kill`, `workers`, `queue`, `set-seed`, `unlock`, alerts list/resolve/snooze |
| `/wallets` | list, balances, generate, import, status, settings, gas-wallet toggle |
| `/chains` | CRUD, test RPC, token registry |
| `/projects` | CRUD (delete = archive), restore, stop, eligibility declare/clear, tasks, per-wallet eligibility, criteria draft/accept |
| `/faucets` | CRUD, tokens, request, request-all, per-wallet status |
| `/proxies` | CRUD, assign, activate, test |
| `/ai` | validations list/detail/resolve, validate |
| `/autonomy` | status, pause, resume, actions, approve, undo |
| `/reports` | eligibility, gas, gas-spend, daily-progress, sybil, activity, server, summary, performance/*, export/{table} |
| `/stats` | `overview` |
| `/claims` | `scan` (read-only, cached 10 min; `?refresh=true`) |
| `/ops` | project details/contracts/criteria/trigger-all/reset-circuit, task edit/trigger, wallet tags/recover/nonces/settings/persona re-roll, `transactions`, chain gas status, `system` (dry-run, emergency clear, archive logs, agent start/stop, seed unlock), `claims/*` |
| `/webhooks` | register/unregister (unused, see Security) |
| `/ws/logs` | WebSocket, `?token=<jwt>`; events `log`, `status`, `heartbeat` |
| `/ws/recent-logs` | history of latest logs |

Interactive docs: `/docs` and `/openapi.json` (currently public; restrict in production).

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
