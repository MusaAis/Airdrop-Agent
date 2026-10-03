# Security

Status as of commit `9c3803f`. This documents what the code does today, including gaps.

## Threat model
Single operator. Threats: a stolen login/JWT, a compromised server, an exposed public port, a leaked `.env`, and bad AI decisions. Testnet funds only.

## Authentication
- Login: username + password, optional TOTP, brute-force lockout (`LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES`, DB-persisted), optional 30-day "remember device" cookie (httpOnly, secure, SameSite=None).
- JWT HS256 signed with `SECRET_KEY`: access token 30 min, refresh token 7 days.
- 129 of 133 HTTP/WS endpoints require a bearer token. Public: `/agent/health`, `/auth/login`, `/auth/refresh`; `/ws/logs` requires `?token=` and closes with code 4001 otherwise.

## Secrets at rest
- Imported private keys: AES-256-CBC, key from PBKDF2-SHA256 (600,000 iterations), random 16-byte salt and IV per key, keyed by `MASTER_PASSWORD`.
- Master mnemonic: stored encrypted in `agent_secrets`; the decrypted copy lives **only in process memory** and must be re-unlocked after each restart.
- HD wallet keys are derived on demand (`m/44'/60'/0'/0/{index}`), never stored.
- `.env`, `airdrop.db*` are git-ignored.

## Guardrails against runaway automation
Emergency stop, dry-run, AI-autonomy freeze, 70% agreement gate, bounded and logged AI actions, forbidden NL actions for secrets, Telegram confirmation flow, whitelisted Telegram ids, SSRF check on the criteria-draft URL fetch (http(s) only, blocks private, internal and cloud-metadata addresses).

## Known gaps (open at this commit)
| ID | Severity | Issue | Recommended fix |
|---|---|---|---|
| C7 | Critical | Access, refresh and device-trust JWTs share one key and no `type` claim is checked on bearer auth; `/auth/refresh` accepts any valid token and takes it as a query parameter | add `type` claim, enforce it, send refresh token in body or httpOnly cookie |
| C8 | Critical | `MASTER_PASSWORD` defaults to empty (admin password and key-encryption secret); `SECRET_KEY` defaults to a known string | refuse to start on empty/short/default values; split login password from key-encryption secret |
| H1 | High | `POST /auth/totp/setup` replaces the 2FA secret with only a JWT | require the current TOTP code before re-enrolling |
| H6 | High | `POST /agent/wallets/{id}/private-key` returns raw keys for JWT + master password | remove, or require TOTP and a separate secret |
| H7 | High | Webhook registry POSTs to arbitrary URLs (SSRF) and is unused | delete it, or reuse the public-URL check |
| - | High | IP-whitelist middleware is **commented out** in `main.py`; `/docs` and `/openapi.json` are public | enable it, bind to `127.0.0.1` behind the tunnel, firewall the port |
| - | Medium | Brute-force counter uses `request.client.host` (proxy IP behind a tunnel); `/auth/login` timing reveals unknown usernames | use the forwarded client IP; hash a dummy on unknown user |
| - | Medium | JWT stored in `localStorage` (XSS-readable); refresh flow unused by the frontend | httpOnly refresh cookie, in-memory access token |
| - | Medium | `/agent_unlock <password>` leaves the password in chat history; `/auth` private key export logs a warning only | delete the message after reading |
| - | Medium | CORS allows only `airdrop-agent-wine.vercel.app` | confirm it matches your deployed frontend |

Fixed in this push: dry-run no longer sends approval transactions; kill and confirmation flows work; the agent loop can be stopped.

## Hardening checklist
1. Set a long random `MASTER_PASSWORD` and `SECRET_KEY` before first start (the admin user is created from it on first boot).
2. `chmod 600 .env`; run as an unprivileged user.
3. Bind uvicorn to `127.0.0.1` and expose it only through a tunnel or reverse proxy; enable the IP-whitelist middleware.
4. Enable TOTP from the dashboard right after first login.
5. Add systemd hardening (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=` for the DB directory, `PrivateTmp=yes`).
6. Keep the Telegram group private; whitelist only your id.
7. Back up `airdrop.db` and your encrypted seed yourself. There is no built-in backup.
8. Treat dry-run and emergency-stop as non-persistent: re-apply after any restart.

## Before mainnet (not supported today)
Tighter autonomy rate limits, stricter agreement gate, human approval as default, separate key-encryption secret, remove key export, pin dependencies, add tests and CI.

## Reporting vulnerabilities
Open a private security advisory on the GitHub repository.
