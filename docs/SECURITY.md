# Security

This documents what the code does today, including gaps.

## Threat model
Single operator. Threats: a stolen login/JWT, a compromised server, an exposed public port, a leaked `.env`, and bad AI decisions. Testnet funds only.

## Authentication
- Login: username + password, optional TOTP, brute-force lockout (`LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES`, DB-persisted), optional 30-day "remember device" cookie (httpOnly, secure, SameSite=None). Unknown usernames cost the same bcrypt work as wrong passwords.
- JWT HS256 signed with `SECRET_KEY`. Every token carries a `type` claim and each consumer accepts exactly one type:

| Token | Lifetime | Accepted by |
|---|---|---|
| `access` | 30 min | all Bearer-protected routes, `/ws/logs?token=` |
| `refresh` | 7 days | `POST /auth/refresh` only (JSON body) |
| `device_trust` | 30 days | login's 2FA bypass only |

  Tokens without a `type` (issued before this change) are rejected, so everyone logs in again once after upgrading.
- Of 130 HTTP/WS endpoints, 127 require a valid access token. Public: `/agent/health`, `/auth/login`, `/auth/refresh`.
- **2FA management**: `POST /auth/totp/setup` needs the account password, plus a current TOTP code if 2FA is already on. The new secret is held in memory (10 min) and only replaces the old one after `/auth/totp/verify-setup` succeeds, so an abandoned or failed replacement never turns 2FA off. `/auth/totp/disable` needs password + current code. All three share a per-user limiter (5 failures / 15 min, then 429; in memory, resets on restart).
- **Startup refusal**: the server will not start if `SECRET_KEY` is empty, a placeholder or under 32 characters, or `MASTER_PASSWORD` is empty, a placeholder or under 8 characters. 8-11 character passwords start with a warning. `ALLOW_INSECURE_SECRETS=true` overrides this for local throwaway development only.

## Secrets at rest
- Imported private keys: AES-256-CBC, key from PBKDF2-SHA256 (600,000 iterations), random 16-byte salt and IV per key, keyed by `MASTER_PASSWORD`.
- Master mnemonic: stored encrypted in `agent_secrets`; the decrypted copy lives **only in process memory** and must be re-unlocked after each restart.
- HD wallet keys are derived on demand (`m/44'/60'/0'/0/{index}`), never stored. There is **no API or bot command that exports a private key**; derive HD keys offline from your recovery phrase.
- `.env`, `airdrop.db*` are git-ignored.
- `MASTER_PASSWORD` is both the admin login password and the key-encryption password. Changing it makes already-stored keys and seed undecryptable unless you re-encrypt them. Changing the env var does not change an existing admin login (that account is created once).

## Guardrails against runaway automation
Emergency stop, dry-run, AI-autonomy freeze, 70% agreement gate, bounded and logged AI actions, forbidden NL actions for secrets, Telegram confirmation flow, whitelisted Telegram ids, SSRF check on the criteria-draft URL fetch (http(s) only, blocks private, internal and cloud-metadata addresses).

## Deliberate choices and known gaps
| Item | Status |
|---|---|
| IP-whitelist middleware | **Intentionally disabled** (commented out in `main.py`). `ALLOWED_IPS` therefore has no effect. Network exposure is controlled at the host/tunnel level. `/docs` and `/openapi.json` are public as a result. |
| Login rate limiting key | counts `request.client.host`, which is the proxy's address behind a tunnel, so one client can lock out others (and vice versa). Use the forwarded client IP if you add a trusted proxy. |
| JWT in `localStorage` | readable by any XSS. The refresh flow exists in the API but the dashboard does not use it. |
| `/agent_unlock <password>` | leaves the password in Telegram chat history; delete the message. |
| Dry-run / emergency stop | not persisted: both reset on restart. |
| Single secret | one `MASTER_PASSWORD` covers login and key encryption (splitting needs a re-encryption migration). |
| 2FA enrolment | API-only (no dashboard screen). Pending enrolments and failure counters are per-process memory. |
| CORS | allows only `https://airdrop-agent-wine.vercel.app`; change it in `main.py` if your frontend lives elsewhere. |
| Refresh tokens | stateless: they cannot be revoked individually; rotate `SECRET_KEY` to sign everyone out. |

## Hardening checklist
1. Set a long random `MASTER_PASSWORD` and `SECRET_KEY` before first start (the admin user is created from `MASTER_PASSWORD` on first boot).
2. `chmod 600 .env`; run as an unprivileged user.
3. Because the IP whitelist is off, bind uvicorn to `127.0.0.1` behind a tunnel or reverse proxy, or firewall the port yourself.
4. Enable TOTP via the API right after first login (see REFERENCE.md).
5. Add systemd hardening (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=` for the DB directory, `PrivateTmp=yes`).
6. Keep the Telegram group private; whitelist only your id.
7. Back up `airdrop.db` and your encrypted seed yourself. There is no built-in backup.
8. Treat dry-run and emergency-stop as non-persistent: re-apply after any restart.

## Before mainnet (not supported today)
Tighter autonomy rate limits, stricter agreement gate, human approval as default, separate key-encryption secret, pin dependencies, broader tests and CI.

## Reporting vulnerabilities
Open a private security advisory on the GitHub repository.
