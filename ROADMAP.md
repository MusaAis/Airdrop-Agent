# Roadmap

History lives in `PLAN.md` (phases 1-10). This file is the forward view.

## Done
Phases 1-9: removals and trim, project wizard, NL + AI analyst, failure analysis, bounded AI autonomy, website build-out, Telegram topics and reports, redesign. Phase 7/9 verification pass fixed gas units, detached-object persistence, nonce sync, dry-run approvals, Telegram confirm flow and agent stop. Phase 10 (documentation) is this doc set.

## Next: stabilise (recommended before new features)
1. **Auth (C7, C8, H1)**: token types, startup refusal on weak secrets, 2FA re-enrol protection.
2. **Remove or lock down** private-key export (H6) and webhooks (H7).
3. **Enable IP whitelist**, bind to localhost, restrict `/docs`.
4. **Persist emergency stop and dry-run**; read `DRY_RUN_MODE` at startup. Consider auto-unlock of the seed at boot if you accept the trade-off.
5. **Write gas cost per transaction** (`gas_used x effective price`; show native gas on testnet) so reports and eligibility volume stop reading 0.
6. Fix import of `0x` keys (H8) and CoinGecko ids (H9, add a `coingecko_id` to `Chain`).
7. Unify the gas multiplier (persona vs `WalletSettings`).
8. Wire Alembic (`target_metadata`, first revision) so schema changes stop being manual.
9. Add tests and CI: gas conversion, nonce lock/sync, agreement scoring, error classification, autonomy bounds, project dispatch.
10. Pin dependencies; check `signed.rawTransaction` and `tx_hash.hex()` against current `eth-account`/`hexbytes`.

## Backlog (from PLAN.md and review)
- Human-like scheduling: honour `frequency_mins`, persona sleep times and per-wallet `next_run_at` (`TaskSchedule` is unused); update `last_selected_at`.
- Autonomy recovery: gas multiplier decay, priority restore, auto-recover wallets in cooldown.
- Manual claim execution with confirm + dry-run (never automatic); needs a transaction path without `task_config_id`.
- Faucet cooldown should count only successful requests and verify arrival.
- Enforce or drop `completed_projects_blacklist`; enforce the maintenance window.
- Refresh-token cookie flow; audit log of manual actions; per-wallet "why am I not running?" view.
- Proxies for RPC calls per wallet (today proxies cover faucets only).
- Task templates; draft-only AI task configs (addresses must appear in the docs and have code on chain; saved disabled).
- Report schedule and "test each topic" control in Settings; auto-recreate deleted Telegram topics.
- Cleanup of dead code listed in `airdrop-agent-review.md`.

## Long term
Multi-user accounts and roles, webhook-driven triggers, ABI-aware generic tasks, factual ROI (gas spent vs tokens received), browser/email notifications, cooldown visualisation, and a mainnet readiness pass (see Security).
