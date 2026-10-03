# Architecture

## Process model
One Python process (`python3 -m backend.main`, uvicorn) hosts everything. On startup (`backend/main.py`):
1. `enforce_startup_secrets()` aborts the process if `SECRET_KEY` / `MASTER_PASSWORD` are unsafe (before anything touches the database).
2. `init_db()` enables SQLite WAL, runs `create_all()`, then adds any missing columns to existing SQLite tables. Ensures an `admin` user exists (password = `MASTER_PASSWORD`, created on first start only).
3. `load_autonomy_state()` restores the persisted AI-autonomy freeze flag.
4. `start_scheduler()` starts APScheduler jobs.
5. `start_agent()` starts the agent loop (sets `agent_task`, so stop/kill can cancel it).
6. The Telegram bot starts if `TELEGRAM_BOT_TOKEN` is set.

```
 React dashboard (Vercel) ──HTTPS/WSS──┐
 Telegram (bot + group topics) ─────────┤
                                        ▼
                         FastAPI (routers: 130 endpoints)
                                        │
        ┌───────────────┬───────────────┼────────────────┬──────────────┐
        ▼               ▼               ▼                ▼              ▼
   Agent loop      APScheduler     AI layer         Telegram        SQLite (WAL)
 (fill queue /30s  (gas, faucets,  (Gemini+Groq,    (commands, NL,  (SQLAlchemy
  worker slots)     analysis,       key pools,       alerts)         async)
        │           reports)        autonomy)
        ▼
  BaseTask.execute → web3 RPC pool → EVM testnets
```

## Components
| Area | Modules | Responsibility |
|---|---|---|
| Agent loop | `agent.py` | every 30 s: `fill_queue` + `monitor_pending_transactions` (skipped during emergency stop or dry-run); 60 s heartbeat; frozen-slot watchdog |
| Queue | `core/queue_manager.py` | priority-weighted fill; candidate filtering (active hours, daily target, dependencies, nonce safety, master-seed lock) |
| Workers | `core/worker_pool.py` | `MAX_WORKER_SLOTS` slots, 480 s task timeout, outcome recording, circuit breaker and cooldown counters, `Log` rows |
| Tasks | `tasks/*` | `BaseTask.execute` pipeline; one subclass per task type |
| Safety | `core/kill_switch.py`, `gas_spike_guard.py`, `memory_guard.py`, `nonce_manager.py`, `stuck_tx_handler.py` | emergency stop, dry-run, AI freeze, gas deferral, RAM pause, nonce locks, speed-up/cancel |
| AI | `ai/*`, `core/failure_analysis.py`, `core/autonomy.py`, `reports/analyst.py` | validation, clustering, bounded actions, narration |
| Wallets | `wallet/*` | HD derivation, encryption, persona, balances, Sybil detection |
| Chains | `chains/*` | RPC pool/failover, gas sampling, price oracle, token registry, contract watcher |
| Security | `security/*` | typed JWTs, TOTP, brute-force lockout, device trust, startup secret checks |
| Reports | `reports/*` | all numbers are DB queries; `periodic.py` builds daily/weekly/monthly Telegram reports |
| Interfaces | `api/routes/*`, `telegram/*`, `frontend/` | control surfaces |

## Scheduled jobs (`core/scheduler.py`)
| Job | Schedule |
|---|---|
| faucet check | every 30 min |
| gas sample | every 10 min |
| contract check | every 4 h |
| failure analysis | every 10 min |
| AI autonomy | every 10 min (offset +2 min) |
| daily report | 08:00 UTC |
| AI activity digest | 08:05 UTC |
| weekly report | Monday 08:10 UTC |
| monthly report | 1st, 08:15 UTC |
| log archival | Sunday 03:00 |
| Sybil re-score | self-rescheduling, random 6-18 h |

## Data model (SQLite, `backend/models.py` plus module-registered tables)
- **Identity/config**: `users`, `agent_secrets` (encrypted master mnemonic), `agent_status`, `login_attempts`
- **Chains**: `chains` (incl. `coingecko_id`), `chain_tokens`, `rpc_request_log`
- **Wallets**: `wallets`, `wallet_settings`, `wallet_balances`, `wallet_nonces`, `proxies`
- **Projects**: `projects`, `project_contracts`, `project_criteria`, `task_configs`, `task_daily_progress`, `task_schedule` (unused), `active_tasks`, `completed_projects_blacklist` (unenforced)
- **Execution**: `transactions` (incl. `gas_used`, `gas_token`, `gas_cost_native`, `gas_cost_usd`, `error_message`), `token_approvals`, `task_failures` (30-day retention), `logs`, `logs_archive`
- **AI**: `ai_validations`, `ai_actions`, `ai_autonomy_state`
- **Other**: `faucets`, `faucet_tokens`, `faucet_requests`, `alerts`, `telegram_routes`, `competitor_wallets`

### Schema changes
New tables come from `create_all()`. For **SQLite**, `init_db()` also adds any model column missing from an existing table (`ALTER TABLE ... ADD COLUMN`, idempotent, logged as "Added missing columns"). It only handles added columns that are nullable or have a default: renames, type changes, drops and NOT NULL columns without a default still need a manual migration. Alembic is not wired up (`target_metadata = None`, no versions). Postgres is not auto-migrated.

## Frontend
Vite + React 18, `react-router-dom`, `axios`, `recharts`. Shared design system in `src/index.css` and `components/ui.jsx` (`DataTable`, `Modal`, `Toast`, `useConfirm`, `useApi`). Navigation config in `components/nav.js` drives the desktop sidebar and phone bottom bar. Live feed: `hooks/useLiveFeed.js` (WebSocket with backoff, history preloaded from `/ws/recent-logs`).

Pages: Dashboard, Wallets, Balances, Chains, Tasks, Projects (+ new, detail), Logs, Reports, Faucets, Proxies, Settings, Claims, AI Log, Sybil, Snapshot, Notifications.
