# Deployment and configuration

## Requirements
Python 3.12 (tested: 3.12), Node 18+ for the frontend build, an always-on host (the project runs on an Oracle Cloud VM), optional Telegram bot token, Gemini and/or Groq API keys.

## Backend
```bash
cd /home/ubuntu/airdrop-agent
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt     # rerun after every pull (httpx[socks] was added)
cp .env.example .env && chmod 600 .env
sudo cp systemd/airdrop-agent.service /etc/systemd/system/
sudo systemctl enable --now airdrop-agent
journalctl -u airdrop-agent -f
```
The unit runs `/usr/bin/python3 -m backend.main` as user `ubuntu` with `EnvironmentFile=.env`. If you use a venv, change `ExecStart` to the venv's python.

After **every restart**: unlock the master seed (Settings > System, or `/agent_unlock <password>`), and re-set dry-run if you want it on.

## Frontend (Vercel or any static host)
```bash
cd frontend && npm install && npm run build
```
Set `VITE_API_BASE_URL` (e.g. `https://api.example.com`) and `VITE_BACKEND_WS_URL` (e.g. `wss://api.example.com`). If the WS URL is unset it is derived from the API URL. Add the frontend origin to the CORS list in `backend/main.py`.

## Environment variables
| Variable | Default | Notes |
|---|---|---|
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8002` | prefer `127.0.0.1` behind a tunnel |
| `SECRET_KEY` | known placeholder | **must change** |
| `MASTER_PASSWORD` | empty | **must set**; admin login and key encryption |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | 30 / 7 | |
| `DEVICE_TRUST_EXPIRE_DAYS` | 30 | remember-device cookie |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | 5 / 15 | |
| `DATABASE_URL` | `sqlite+aiosqlite:///./airdrop.db` | Postgres path exists but `init_db` runs SQLite PRAGMAs |
| `GROQ_API_KEY` or `GROQ_API_KEYS` | empty | comma-separated list enables key rotation |
| `GEMINI_API_KEY` or `GEMINI_API_KEYS` | empty | same |
| `AI_MAX_TOKENS` | 4096 | |
| `TELEGRAM_BOT_TOKEN` | empty | bot starts only if set to a real token |
| `TELEGRAM_ALLOWED_USER_IDS` | `[]` | JSON list; empty means nobody can command the bot |
| `ALLOWED_IPS` | `127.0.0.1,::1` | used only if the IP middleware is enabled |
| `MAX_WORKER_SLOTS` | 4 | |
| `MEMORY_ALERT_THRESHOLD_PCT` | 82 | |
| `LOG_LEVEL` | INFO | |
| `DRY_RUN_MODE` | false | defined but not applied at startup |

`.env.example` still lists the removed `OCI_*` and `BACKUP_SCHEDULE_HOUR` entries and omits the `*_API_KEYS` and `DEVICE_TRUST_EXPIRE_DAYS` variables.

## First-run checklist
1. Log in as `admin` with `MASTER_PASSWORD`; enable TOTP.
2. Settings > System: set the master seed (or unlock an existing one).
3. Add a chain (RPC list, gas token, warning/critical balances); verify with Test RPCs.
4. Generate or import wallets; mark one or more as gas wallets; fund from faucets.
5. Turn dry-run **on**, add a project and task, run the task manually, read the Logs page.
6. Turn dry-run off when results look right.
7. Telegram: add your id to `TELEGRAM_ALLOWED_USER_IDS`, then `/group_setup` in a private Topics group.

## Updating
```bash
git pull && pip install -r backend/requirements.txt && sudo systemctl restart airdrop-agent
```
New columns on existing tables are not migrated automatically (no Alembic revisions); new tables are.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| HD wallets never run after restart | master seed locked; unlock it |
| Everything silently stops | emergency stop or dry-run is set (both reset on restart) |
| Tasks skipped as `low_gas` | wallet gas balance below estimate x 1.2 |
| `nonce too low` | stored nonce behind chain; sync from Wallets > Manage |
| Live log blank | wrong `VITE_BACKEND_WS_URL` or CORS origin |
| SOCKS proxy faucet errors | `httpx[socks]` not installed; rerun pip install |
