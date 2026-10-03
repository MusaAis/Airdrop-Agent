# Airdrop Agent

A self-hosted agent that farms testnet airdrops. It manages many EVM wallets, runs configured on-chain tasks (swap, bridge, stake, liquidity, transfer, generic contract calls) against registered projects on a human-looking schedule, tracks eligibility criteria, and reports through a Telegram bot and a React dashboard. AI (Gemini + Groq) analyses and narrates; it never invents numbers and never creates projects or task configs.

> **Environment: testnet only.** Several guardrails are deliberately loose for testnet. See [docs/SECURITY.md](docs/SECURITY.md) before considering mainnet.

## Features
- **Wallets**: HD wallets from one master seed or imported private keys (encrypted at rest), tags, per-wallet persona (active hours, gas multiplier, daily tx range), health and Sybil scores.
- **Chains**: primary + fallback RPCs, gas sampling every 10 min with spike detection, token registry, optional CoinGecko id for USD pricing.
- **Projects and tasks**: priority-weighted queue, daily targets, dependencies, eligibility criteria, circuit breaker, soft-archive, manual eligibility declaration.
- **Execution engine**: fixed worker slots, nonce locking synced to chain, pre-flight simulation, dry-run, stuck-tx speed-up/cancel, watchdog, per-transaction fee tracking.
- **AI layer**: dual-model validation (70% agreement gate), failure-cluster analysis, bounded autonomous actions (pause wallet, gas multiplier, disable task, lower priority), all logged and undoable.
- **Interfaces**: web dashboard (phone + desktop), Telegram bot (quick-action remote) and a Telegram group with topics for reports.

## Repository layout
| Path | Purpose |
|---|---|
| `backend/` | FastAPI app, agent loop, scheduler, models |
| `backend/core/` | queue, worker pool, nonce manager, kill switch, autonomy, failure analysis |
| `backend/tasks/` | task types (swap, bridge, stake, liquidity, transfer, generic) |
| `backend/ai/` | Gemini/Groq clients, key pools, orchestrator, prompts |
| `backend/security/` | JWT auth, TOTP, brute-force lockout, startup secret checks |
| `backend/telegram/` | bot, NL parser, wizard, topics, alerts |
| `backend/api/routes/` | REST + WebSocket endpoints |
| `frontend/` | Vite + React dashboard |
| `systemd/` | service unit |
| `PLAN.md` | phase-by-phase build log (source of truth for history) |

## Quick start
```bash
git clone https://github.com/MusaAis/airdrop-agent && cd airdrop-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env        # REQUIRED: set SECRET_KEY and MASTER_PASSWORD (see docs/DEPLOYMENT.md)
python3 -m backend.main     # serves on SERVER_PORT (default 8002)

cd frontend && cp .env.example .env.local && npm install && npm run dev
```
The server **refuses to start** with an empty/short/placeholder `SECRET_KEY` or `MASTER_PASSWORD`. On every restart the master seed is locked: HD wallets will not be scheduled until you unlock it (Settings > System, or `/agent_unlock`).

## Tests
```bash
python3 -m backend.test_security_fixes                                  # auth, secrets, 2FA, import, fees, migration
TELEGRAM_ALLOWED_USER_IDS='["42"]' python3 -m backend.test_c2c3c4       # gas units, nonce, Telegram confirm flow
```
Both use throwaway SQLite files and need no network or chain.

## Documentation
- [Architecture](docs/ARCHITECTURE.md)
- [How it works](docs/HOW-IT-WORKS.md)
- [Security](docs/SECURITY.md)
- [Deployment and configuration](docs/DEPLOYMENT.md)
- [API and Telegram reference](docs/REFERENCE.md)
- [Roadmap and known issues](ROADMAP.md)

## License
See [LICENSE](LICENSE).
