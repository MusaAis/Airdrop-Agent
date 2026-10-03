# Roadmap

History lives in `PLAN.md` (phases 1-10). This file is the forward view.

## Done
Phases 1-9: removals and trim, project wizard, NL + AI analyst, failure analysis, bounded AI autonomy, website build-out, Telegram topics and reports, redesign. Phase 10: documentation (`docs/`).

Verification and hardening passes (see `airdrop-agent-review.md`): gas units, detached-object persistence, nonce sync, dry-run approvals, Telegram confirm flow, agent stop, then typed JWTs (C7), startup secret checks (C8), protected 2FA enrolment (H1), per-transaction fee recording (H2), removal of key export (H6) and the webhook registry (H7), `0x` key import (H8), CoinGecko ids and checksummed ERC20 calls (H9), and automatic SQLite column additions.

## Next
1. **Persist emergency stop and dry-run**; read `DRY_RUN_MODE` at startup. Consider auto-unlock of the seed at boot if you accept the trade-off.
2. **Human-like scheduling (H4)**: honour `frequency_mins`, persona sleep times and per-wallet `next_run_at` (`TaskSchedule` is unused); update `last_selected_at`.
3. **Reports on native gas**: aggregate `gas_cost_native` (factual) instead of, or next to, the testnet-meaningless USD figure; unify the two eligibility implementations.
4. Unify the gas multiplier (persona vs `WalletSettings`).
5. Wire Alembic (`target_metadata`, first revision) for renames/drops/Postgres; the automatic column adder only covers additive SQLite changes.
6. Add tests and CI beyond the two current suites: nonce lock/sync edge cases, agreement scoring, error classification, autonomy bounds, project dispatch.
7. Pin dependencies; check `signed.rawTransaction` and `tx_hash.hex()` against current `eth-account`/`hexbytes`.
8. Login limiter keyed on the real client IP behind a proxy; httpOnly refresh cookie with an in-memory access token.
9. Separate key-encryption secret from the login password (needs a re-encryption migration).

## Backlog (from PLAN.md and review)
- Autonomy recovery: gas multiplier decay, priority restore, auto-recover wallets in cooldown.
- Manual claim execution with confirm + dry-run (never automatic); needs a transaction path without `task_config_id`.
- Faucet cooldown should count only successful requests and verify arrival.
- Enforce or drop `completed_projects_blacklist`; enforce the maintenance window.
- Dashboard screen for 2FA enrolment; audit log of manual actions; per-wallet "why am I not running?" view.
- Proxies for RPC calls per wallet (today proxies cover faucets only).
- Task templates; draft-only AI task configs (addresses must appear in the docs and have code on chain; saved disabled).
- Report schedule and "test each topic" control in Settings; auto-recreate deleted Telegram topics.
- Cleanup of dead code listed in `airdrop-agent-review.md`.

## Deliberate decisions
- The IP-whitelist middleware stays disabled; network exposure is handled at the host/tunnel level.

## Long term
Multi-user accounts and roles, webhook-driven triggers (with a public-URL check), ABI-aware generic tasks, factual ROI (gas spent vs tokens received), browser/email notifications, cooldown visualisation, and a mainnet readiness pass (see `docs/SECURITY.md`).
