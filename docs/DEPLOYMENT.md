# Deployment and configuration

## Requirements
Python 3.12 (tested: 3.12), Node 18+ for the frontend build, an always-on host (the project runs on an Oracle Cloud VM), optional Telegram bot token, Gemini and/or Groq API keys.

## Backend
```bash
cd /home/ubuntu/airdrop-agent
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt     # rerun after every pull
cp .env.example .env && chmod 600 .env       # then set SECRET_KEY and MASTER_PASSWORD
sudo cp systemd/airdrop-agent.service /etc/systemd/system/
sudo systemctl enable --now airdrop-agent
journalctl -u airdrop-agent -f
```
The unit runs `/usr/bin/python3 -m backend.main` as user `ubuntu` with `EnvironmentFile=.env`. If you use a venv, change `ExecStart` to the venv's python.

If the service exits immediately with "Refusing to start with unsafe secrets", read the journal: it lists exactly which value is wrong.

After **every restart**: unlock the master seed (Settings > System, or `/agent_unlock <password>`). Dry-run and the emergency stop are restored automatically; if the emergency stop was active, clear it before expecting any work.

## Frontend (Vercel or any static host)
```bash
cd frontend && npm install && npm run build
```
Set `VITE_API_BASE_URL` (e.g. `https://api.example.com`). `VITE_BACKEND_WS_URL` (e.g. `wss://api.example.com`) is optional; if unset it is derived from the API URL. Add the frontend origin to the CORS list in `backend/main.py`.

## Environment variables
| Variable | Default | Notes |
|---|---|---|
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8002` | prefer `127.0.0.1` behind a tunnel |
| `SECRET_KEY` | placeholder | **required**, >= 32 chars; startup fails otherwise. Rotating it only signs everyone out. Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `MASTER_PASSWORD` | empty | **required**, >= 8 chars (>= 12 recommended). Admin login password **and** key-encryption password: do not change it once wallets/seed are stored unless you re-encrypt them |
| `ALLOW_INSECURE_SECRETS` | false | disables the startup refusal; local throwaway development only |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | 30 / 7 | |
| `DEVICE_TRUST_EXPIRE_DAYS` | 30 | remember-device cookie |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | 5 / 15 | |
| `DATABASE_URL` | `sqlite+aiosqlite:///./airdrop.db` | Postgres path exists but `init_db` runs SQLite PRAGMAs and only SQLite gets automatic column additions |
| `GROQ_API_KEY` or `GROQ_API_KEYS` | empty | comma-separated list enables key rotation |
| `GEMINI_API_KEY` or `GEMINI_API_KEYS` | empty | same |
| `AI_MAX_TOKENS` | 4096 | |
| `COINGECKO_API_KEY` | empty | optional, higher price-lookup limits |
| `TELEGRAM_BOT_TOKEN` | empty | bot starts only if set to a real token |
| `TELEGRAM_ALLOWED_USER_IDS` | `[]` | JSON list; empty means nobody can command the bot |
| `ALLOWED_IPS` | `127.0.0.1,::1` | **no effect**: the IP-whitelist middleware is intentionally disabled |
| `MAX_WORKER_SLOTS` | 4 | |
| `MEMORY_ALERT_THRESHOLD_PCT` | 82 | |
| `LOG_LEVEL` | INFO | |
| `DRY_RUN_MODE` | false | `true` forces dry-run ON at every boot (it never forces it off; the dashboard toggle is saved). Recommended for the first boot of a new deployment |

## First-run checklist
1. Log in as `admin` with `MASTER_PASSWORD`; enable TOTP (see REFERENCE.md, "Enabling 2FA").
2. Settings > System: set the master seed (or unlock an existing one).
3. Add a chain (RPC list, gas token, warning/critical balances, optional CoinGecko id); verify with Test RPCs.
4. Generate or import wallets (imported keys may include a `0x` prefix); mark one or more as gas wallets; fund from faucets.
5. Start with dry-run **on** (`DRY_RUN_MODE=true` for the first boot, or the System panel), add a project and task, run the task manually, read the Logs page.
6. Turn dry-run off when results look right (System panel; the choice is saved). If `DRY_RUN_MODE=true` is still in `.env` it will switch itself back on at the next restart, so set it to `false` first.
7. Telegram: add your id to `TELEGRAM_ALLOWED_USER_IDS`, then `/group_setup` in a private Topics group.

## Updating
```bash
git pull && pip install -r backend/requirements.txt && sudo systemctl restart airdrop-agent
```
On restart, SQLite databases get any new model columns and tables added automatically (check the log for "Added missing columns"). Renames, drops and NOT NULL columns without a default still need manual SQL. Back up `airdrop.db` before upgrading.

Upgrading across the auth hardening change signs everyone out once (old tokens have no `type`).

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Service exits at start: "Refusing to start with unsafe secrets" | `SECRET_KEY` < 32 chars/placeholder, or `MASTER_PASSWORD` empty/< 8/placeholder |
| HD wallets never run after restart | master seed locked; unlock it |
| Everything silently stops | emergency stop or dry-run is set (both survive restarts now; check the System panel) |
| A wallet is idle although it has work | pacing: it is in its sleep window, its task is not due yet (`frequency_mins`), or it has not reached its start offset for the day |
| Reports say "none recorded" for gas | no transaction with fee data in that period (older rows have none) |
| Tasks skipped as `low_gas` | wallet gas balance below estimate x 1.2 |
| `nonce too low` | stored nonce behind chain; sync from Wallets > Manage |
| Live log blank | wrong `VITE_BACKEND_WS_URL` or CORS origin |
| SOCKS proxy faucet errors | `httpx[socks]` not installed; rerun pip install |
| Every password hash raises `ValueError` | bcrypt 5.x with passlib 1.7.4; `requirements.txt` pins `bcrypt<5` |
| USD gas/balance values empty | chain has no resolvable CoinGecko id; set one on the Chains page |
