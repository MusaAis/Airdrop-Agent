# Airdrop-Agent — Project Plan

**Status:** planing v1 compled, building in progress (backend live on Oracle Cloud server, frontend live on Vercel).
**Environment:** Testnet only

## 0. Phase 1&2 completion notes
Phase 1 (§3 removals + §4 Telegram trim) is done and deployed as of 2026-09-27:
- Backend: discovery system, ROI estimator, backup system, and auto-claim execution all removed; Telegram cut to the curated ~45-command set; `bot.py` rewritten in full; `AiLog.jsx` and `Reports.jsx` updated on the frontend. `reports/roi.py` was renamed to `reports/gas_spend.py` (factual gas-cost reporting, no AI guess) — any future work referencing "ROI report" should use this instead.
- New in this phase: `is_ai_autonomy_paused()` / `set_ai_autonomy_paused()` in `backend/core/kill_switch.py`, plus `ai_autonomy_off`/`ai_autonomy_on` Telegram commands (§7's off-switch decision) — this is scaffolding only, the actual autonomous engine from §5.3 has not been built yet.
- Sybil re-score now self-reschedules with a randomized 6-18h delay (was fixed 12h) — see `_schedule_next_sybil_rescore()` in `backend/core/scheduler.py`.
- `requirements.txt` cleaned: added `pyotp`/`qrcode` (were missing despite being required by existing TOTP code — pre-existing bug, now fixed), removed `beautifulsoup4`/`lxml`/`oci` (only used by removed discovery/backup code).
- Deployed: pushed to `github.com/MusaAis/Airdrop-Agent` `main` branch, pulled and restarted on the Oracle Cloud server (systemd service `airdrop-agent`), frontend deployed to Vercel production (`airdrop-agent-musaais.vercel.app`).
- Known pre-existing item, unrelated to this phase: `backend/main.py` has `setup_middleware(app)` commented out, meaning `IPWhitelistMiddleware` is not currently active — worth a look given the server's public-internet exposure (log noise from scanning bots was observed during deployment, ordinary background noise but a reminder the middleware is off).

## 0.3 Phase 3 completion notes
Phase 3 (manual project add, §5.5) per the phase order in §9 — Phase 2 was folded into Phase 1's commit already.
- AddProject.jsx: the criteria step could never be reached, so the AI-draft feature was dead. The steps are now Details → Chains → Socials → Task → Review → Criteria. Criteria comes after the project is created, because the draft endpoint needs a project ID.
- AddProject.jsx: if creating the task failed after the project was created, retrying would have made a duplicate project. It now reuses the project it already created.
- commands/project.py: handle_project_approve still imported prompt_roi, which Phase 1 deleted from prompts.py. /project_approve would have crashed with an ImportError. I removed the ROI call and its "ROI logged" message.
- Telegram wizard: it promised an AI draft it never ran. It now saves the docs URL into the project's notes and points you to /projects/new?project=ID on the dashboard to draft criteria.
- projects.py: the criteria-draft endpoint fetches a URL you supply from your server. I added a check that refuses non-http(s) URLs and private, internal or cloud-metadata addresses, and it strips HTML tags before sending the text to the AI.
- We also added a "Draft criteria" link on each row of the projects table, so a project added/created from Telegram can get its criteria drafted.
**all edited/new file in phase 3**
- backend/telegram/project_wizard.py	new
- backend/telegram/commands/project.py	replace
- backend/telegram/bot.py	        replace
- backend/api/routes/projects.py	replace
- frontend/src/pages/AddProject.jsx	new
- frontend/src/pages/Projects.jsx	replace
- frontend/src/App.jsx	                replace

## 0.4 Phase 4 completion notes
Phase 4 (§5.1 NL improvements + §5.2 AI analyst/reporting, per the phase order in §9) is done:
- **Conversation memory** (`backend/telegram/conversation.py`, new): last 2 turns per user, 10-min TTL, in-memory (same pattern as the existing wizard/confirmation state — lost on restart, fine at this scale). Rendered into the NL prompt as RECENT CONTEXT so a follow-up like "make it 10" can complete the previous command.
- **Fuzzy entity resolution** (`backend/telegram/entity_resolver.py`, new): builds a compact ENTITY INDEX (wallet id/address/tags, project id/name, chain id/name) injected into the prompt, plus a post-parse `resolve_entities()` pass that fuzzy-matches any non-numeric id the LLM returns against real rows. Ambiguous matches downgrade to a clarify message listing the candidates rather than guessing — no silent wrong picks on a fund-adjacent bot.
- **`prompt_telegram_cmd` rewritten** (`backend/ai/prompts.py`): action list cut from the old ~150 down to the curated ~45 from §4 — several of the old actions (discovery.*, report.roi, system.backup, claim.auto_on/off, project.farm/prioritize/cap/update/criteria/blacklist/circuit_breaker, chain.rpc/add_fallback/..., task.dry_run/deps/set_priority/trigger_all/template, nonce.check/sync/release, tx.status/failed/verify, gas.spike/optimal/cost/budget/history, alert.snooze/unsnooze/test/resolve/memory, system.test_rpc/maintenance*/log_archive) had no `dispatch_action()` handler since Phase 1's trim, so the LLM picking one silently failed. `agent.unlock` and `wallet.import` are explicitly forbidden in the prompt — both take a secret (master password / raw private key) that must never be typed into a chat routed through an AI API.
- **AI-written report summaries** (`backend/reports/analyst.py`, new): trend/anomaly detection (failure-rate and gas-cost moves vs. a 7-day baseline) is computed in plain Python — the AI only narrates verified numbers, it never computes or invents one. Uses `ask_gemini`/`ask_groq` directly rather than `dual_ai_validate`, because agreement scoring compares structured decision fields and a prose summary has none — forcing it through that path would incorrectly land every summary in `/ai_pending`. Each summary is still logged as an `AIValidation` (`task_type="analyst_summary"`, `requires_human=False`, `resolved=True`) so it shows up in the AI Log / `ai_status` counts, matching the project's habit of logging every AI call in one place — the agreement_score there is an availability signal (100 = Gemini responded, 50 = only Groq did), not a correctness measure.
- New: `GET /reports/summary?hours=` endpoint, `/report_summary` Telegram command (also reachable via NL as `report.summary`), and an "AI Summary" tab on the Reports page.
- The 08:00 UTC daily Telegram summary now appends the narrative to the same message rather than sending a second one — one coherent report, one round trip. Falls back to a plain factual rendering (still computed, no AI) if both Gemini and Groq are down, so the daily summary never goes out empty.
- **Fixed while in the area**: `handle_report_sybil` (Telegram) was iterating `get_sybil_report()`'s dict return value as if it were a list — now reads `high_risk_wallets` correctly. `nl_parser.py` had a possible unbound-variable reference in its error-logging path on a Gemini JSON-decode failure — fixed.

**Also shipped in this phase, per your requests during planning (moved up from the planned Phase 7 stats-dashboard groundwork):**
- **Soft-archive for projects**: `project.status` gains `"archived"` and `"stopped"` as distinct values. "Deleting" a project via the website (`DELETE /projects/{id}`) now archives it — the row, its tasks, criteria, contracts, and transaction history all stay exactly as they were, so nothing is lost for the future stats dashboard. `POST /projects/{id}/restore` undoes it. "Stopped" is a separate deliberate-halt state, distinct from `paused` (circuit-breaker/temporary) and from `archived` (hidden from the default list) — a stopped project stays visible.
- **Eligibility declaration** (website-only, per your call): new `Project` columns `eligibility_status` (`pending`/`eligible`/`not_eligible`), `eligibility_value_usd`, `eligibility_declared_at`. `POST /projects/{id}/eligibility` declares an outcome; `POST /projects/{id}/eligibility/clear` undoes a mis-click. Declaring either outcome immediately and permanently stops the agent from scheduling new tasks for that project, enforced at the actual dispatch choke point (`queue_manager._project_is_dispatchable()`), independent of `status` — a declared project doesn't farm again even if manually resumed. Telegram's `project.status` / `/project_status` shows the declaration read-only; there is no Telegram setter, by design.
- `Projects.jsx` gained Archive / Restore / Stop / Resume / Declare eligibility / Clear eligibility controls and a "show archived" toggle; a small modal collects the eligible/not-eligible choice and optional USD value.

**Explicitly deferred, not part of this phase:** the full stats/overview dashboard tab (totals, active/inactive/eligible/not-eligible breakdowns, per-project active-days and tx rollups) — this phase only adds the data model and per-project controls it will read from. Folded into **Phase 7 or in its new fresh phase, like/e.g phase 9** (website build-out).

**All new/edited files in Phase 4:**
- `backend/telegram/conversation.py` — new
- `backend/telegram/entity_resolver.py` — new
- `backend/reports/analyst.py` — new
- `backend/ai/prompts.py` — replace (`prompt_telegram_cmd` rewritten)
- `backend/telegram/nl_parser.py` — replace
- `backend/telegram/bot.py` — replace
- `backend/telegram/alerts.py` — replace
- `backend/telegram/commands/report.py` — replace (adds `handle_report_summary`, fixes sybil bug)
- `backend/telegram/commands/project.py` — replace (`project.status` / `project.resume` read/respect eligibility)
- `backend/models.py` — replace (`Project` gains eligibility + archived_at columns)
- `backend/projects/manager.py` — replace (archive/restore/stop/declare_eligibility/clear_eligibility)
- `backend/core/queue_manager.py` — replace (`_project_is_dispatchable()` choke point)
- `backend/api/routes/projects.py` — replace (archive/restore/stop/eligibility endpoints; delete route now soft-archives)
- `backend/api/routes/reports.py` — replace (`GET /reports/summary`)
- `frontend/src/pages/Projects.jsx` — replace
- `frontend/src/pages/Reports.jsx` — replace (AI Summary tab, "Gas spend" duplicate label fixed to "Gas by chain")

## 0.5 Phase 5 completion notes
Phase 5 (§5.4 AI error notification/reporting) is done:
- **`task_failures` table** (`TaskFailure` in `backend/models.py`, new): one row per failed or skipped task run (wallet, chain, project, task, outcome, category, reason). Written from the single results point in `worker_pool._execute_task`. Created by `create_all()`; purged after 30 days by the weekly maintenance job. Skips are recorded at most once per wallet+chain+category per 30 min so the table doesn't fill with repeats.
- **`backend/core/failure_analysis.py`** (new, shared with Phase 6): deterministic classifier (gas_spike, contract_paused, memory_pressure, task_timeout, low_gas, rpc_error, nonce_error, simulation_revert, onchain_revert, approval_failed, config_error, unknown), clustering, and the transient/systemic verdict. Cluster = 3+ events, same category, same chain, within 60 min. `find_clusters()` returns structured dicts Phase 6 can act on directly.
- **Alerts**: `_run_failure_analysis` runs every 10 min. Transient clusters -> info alert with a fixed explanation. Systemic clusters -> warning (critical at 10+ events or 5+ wallets) with an AI-narrated likely cause (Gemini, Groq fallback; the AI only narrates verified facts and logs an `AIValidation` `task_type="failure_analysis"`). Same cluster alerts at most once per 2h unless its count doubles. Nothing is sent during emergency stop. Dedup state is in memory. All alerts go through `create_and_send_alert`, so Phase 8 topic routing has one place to change.
- **Behavior fix in `worker_pool`**: `skipped` results (gas spike, low gas, paused contract) no longer increment `wallet.failure_count` or the project circuit breaker. Before, 3 low-gas skips put a wallet in cooldown and 5 tripped the breaker. Only `failed` results and real exceptions/timeouts count. `simulated` (dry-run) counts as neither.
- **Bugs fixed in passing**: `tx_monitor.py` missing imports (pending txs never updated); `contract_watcher.check_all_contracts` did not exist (4-hourly job failed on import); `token_registry.get_token_address` / `get_wrapped_native` did not exist (swaps using token symbols always failed); `create_and_send_alert` now honors `alert_snooze` (critical alerts always sent).

**New/edited files in Phase 5:**
- `backend/models.py` — append `TaskFailure`
- `backend/core/failure_analysis.py` — new
- `backend/core/worker_pool.py` — replace
- `backend/core/scheduler.py` — replace
- `backend/core/tx_monitor.py` — replace
- `backend/chains/contract_watcher.py` — replace
- `backend/chains/token_registry.py` — replace
- `backend/telegram/commands/alert.py` — replace (adds `is_snoozed()`)
- `backend/telegram/alerts.py` — 3-line edit (see chat)

## 0.6 Phase 6 completion notes
Phase 6 (§5.3 AI-managed tasks/wallets, built on Phase 5's `find_clusters()`) is done:
**How it works** (`backend/core/autonomy.py`, new; runs every 10 min from the scheduler, offset 2 min after failure analysis):
1. **Code proposes, the AI never picks.** Targets and new values are computed deterministically from verified failure data, inside hard bounds. This keeps the project's rule that the AI never invents numbers.
2. **Dual-AI review is a veto gate** (`dual_ai_validate`, `task_type="autonomy"`). Only the single field `approved` is compared for agreement (prose is never compared). Agreement >= 70% and approved -> applied. Agreement >= 70% and rejected -> `vetoed` (logged, nothing changes). Agreement < 70% or Groq unavailable -> saved as a **suggestion**, Telegram notifies, waits for you (§7.4).
3. Every applied action is written to the new `ai_actions` table (what, why, before/after, AI reasoning, agreement, reversible), sent to Telegram, and undoable.

**The four allowed actions** (complete list; no code path exists for anything else):
- `wallet_pause` — a wallet with 2+ consecutive failures (before the hard cooldown at 3) whose failures sit in a *systemic* cluster of `low_gas` / `rpc_error` / `nonce_error`. Auto-resumes when the cause clears (gas balance back above the warning threshold, or RPC reachable with no rpc errors for 30 min, or 60 min for nonce errors; minimum 30 min paused) and resets `failure_count` to 0, because those failures were not the wallet's fault. Gas wallets are never paused.
- `gas_multiplier` — raise `WalletSettings.gas_multiplier` by 0.1 (range 0.7-1.8) after 2+ "underpriced" rejections for that wallet. Uses the new `gas_underpriced` failure category.
- `task_disable` — disable an existing task config with 3+ task-level failures (`config_error`, or simulation/on-chain revert/approval failure across 2+ wallets, so one bad wallet cannot get a healthy task disabled).
- `project_priority` — lower a project's priority by 1 (min 1) after 10+ project-attributable failures across 2+ wallets in 24h. Infrastructure causes (RPC, gas, nonce) are excluded, so an RPC outage cannot demote a project.

**Never autonomous:** adding projects or task configs, key/seed handling, claim execution, deleting anything.
**Tasks configs should be simi autonomous if possible** but think very well about it, and if its can works well forget about it.

**Guardrails:** 10 adjustments per target per 24h (§7.1); max 5 AI reviews per cycle (caps cascades and Gemini/Groq quota); per-type cooldowns (pause 2h, gas 3h, task 6h, priority 24h) and any open suggestion blocks a repeat; 12h cooldown after a human undo; bounds re-checked against **live** state at apply time (also when you approve a suggestion); an undo refuses to overwrite a target someone changed since; suggestions expire after 24h; nothing runs during emergency stop.
**Off switch (§7.3):** one flag (`is_ai_autonomy_paused()`), reachable from Telegram (`/ai_autonomy_off` / `/ai_autonomy_on`) and the dashboard (Settings > AI autonomy). It is now **persisted** in `ai_autonomy_state` and restored at startup, so a crash + systemd restart can no longer silently re-enable autonomy. It is also re-checked after the LLM calls, so flipping it mid-cycle turns a pending apply into a suggestion.
**Telegram** (no new slash commands, so `bot.py` is untouched): actions are referenced as `A<id>`. `/ai_approve A5` applies a suggestion. `/ai_reject A5` dismisses a suggestion or **undoes** an applied action. `/ai_pending` lists suggestions and the last 24h of autonomous actions. `/ai_status` shows frozen/active and 24h counts. Plain numbers still mean AI validations, as before.
**Dashboard:** new `AutonomyPanel` on the Settings page: freeze/resume, status counts, action log with Approve / Dismiss / Undo, and an expandable row showing why, the AI's reasoning and before -> after.
**API:** `GET /autonomy/status`, `POST /autonomy/pause`, `POST /autonomy/resume`, `GET /autonomy/actions`, `POST /autonomy/actions/{id}/approve`, `POST /autonomy/actions/{id}/undo`.
**Failure analysis changes:** new category `gas_underpriced`; clusters now carry `wallet_counts` and `task_stats` (per-target evidence for the engine).
**Migration:** none needed. `ai_actions` and `ai_autonomy_state` are new tables, created by `create_all()` on the next start (unlike Phase 4's new columns).

**New/edited files in Phase 6:**
- `backend/core/autonomy_models.py` — new
- `backend/core/autonomy.py` — new
- `backend/api/routes/autonomy.py` — new
- `backend/core/failure_analysis.py` — replace
- `backend/core/scheduler.py` — replace
- `backend/main.py` — replace
- `backend/telegram/commands/ai.py` — replace
- `frontend/src/components/AutonomyPanel.jsx` — new
- `frontend/src/pages/Settings.jsx` — replace
- `frontend/vite.config.js` — replace

## 0.7 Phase 7 completion notes
Phase 7 (website build-out for what moved off Telegram, §4/§6) is done in this scope. The full visual redesign is deliberately **not** in it; it moves to Phase 9 (see decisions).

**Decisions you asked me to make**
- **Stats dashboard (deferred in Phase 4): built now.** It is read-only over data that already exists, so it carried almost no risk. `GET /stats/overview` + a `StatsOverview` section at the top of the Dashboard: project/wallet breakdowns, eligible/not-eligible counts and declared value, transactions and success rate for 24h / 7d / all time, gas spend, open alerts, AI suggestions, and a per-project rollup (tasks enabled/total, tx ok/failed, wallets used, active days, gas $, last tx).
- **Semi-autonomous task configs: not built.** A task config needs a verified router/bridge/staking address and token addresses, and a wrong guess spends real gas or does nothing quietly. The AI would be guessing those from docs. If you still want it later, the only safe shape is draft-only (same boundary as criteria drafts): a draft is accepted only if the contract addresses are quoted verbatim in the docs AND `eth_getCode` shows code at them on the target chain, and it is saved **disabled** until a human enables it. Parked for Phase 9/11 as optional.
- **Full redesign + remaining polish: new Phase 9.** Redesigning every page is a project of its own; doing it on top of this functional work would have made both worse.

**What was built (all under `/ops`, `/stats`, `/proxies`)**
- **Wallets**: Manage panel per wallet. Recover (cooldown/paused -> active **and failure_count reset to 0**; before, activating a cooldown wallet left it at 3 failures so one new failure put it straight back), blacklist, gas-wallet toggle, tag editor, full persona/settings editor, nonce view with release-lock and sync-from-chain.
- **Chains**: edit RPC list (primary + fallbacks), explorer, gas token config, warning/critical balances, RPC rate limit, enable; Test RPCs; live gas status (current vs 6h average, spike flag, cheapest UTC hours); token registry list/add; delete chain.
- **Tasks**: edit amounts, daily range, frequency, slippage, deadline, tokens, reverse tokens, dependencies (validated: same project, no self, no cycles), parameters JSON; enable/disable; **Run now** (any active wallet or random; respects emergency stop and says whether it is dry-run).
- **Projects**: new detail page: priority, wallet cap, links, notes, **TGE / airdrop dates** (the Snapshot Calendar could never be fed before; there was no way to set them), circuit-breaker status + reset, criteria editor (add/edit/delete).
- **Proxies**: real page. Add, assign (one proxy per wallet), activate/deactivate, test (shows exit IP + latency), delete. Passwords are masked in every API response. **Wired in**: faucet claims now go through the wallet's active proxy and fail rather than fall back to the server's own IP.
- **System** (Settings): global dry-run toggle (replaces the old per-task dry-run command), emergency-stop status + clear, archive logs now.
- **Fixes found on the way**: `rotate_proxy` crashed for a wallet without a proxy and *stole other wallets' proxies*; `Sybil.jsx` showed no pairs (endpoint returns a dict, page expected a list); Snapshot/Sybil used `/projects` and `/wallets` without a trailing slash (a redirect that can drop the auth header); logout left the JWT in localStorage (axios and the live-log WebSocket kept using it); an expired token (30 min, no refresh flow) failed silently. A 401 now returns you to login.

**New/edited files in Phase 7**
- `backend/api/routes/ops.py` — new
- `backend/api/routes/stats.py` — new
- `backend/api/routes/proxies.py` — new
- `backend/proxy_manager.py` — replace
- `backend/faucet/manager.py` — replace
- `backend/main.py` — replace (also keeps Phase 6 changes)
- `frontend/src/components/StatsOverview.jsx`, `SystemPanel.jsx`, `WalletManage.jsx` — new
- `frontend/src/pages/ProjectDetail.jsx` — new
- `frontend/src/pages/Proxies.jsx`, `Chains.jsx`, `Tasks.jsx` — replace
- Patched in place by `apply_phase7_patches.py`: `api.js`, `App.jsx`, `Dashboard.jsx`, `Projects.jsx`, `Wallets.jsx`, `Settings.jsx`, `Snapshot.jsx`, `Sybil.jsx`, `vite.config.js`

## 0.8 Phase 8 completion notes
Phase 8 (Telegram group with topics: reports, errors, AI activity) is done.

**How it works**
- One private **supergroup with Topics** replaces the DM-only firehose. Run `/group_setup` inside the group (bot must be admin with "Manage topics"); it creates the topics and stores the group + topic ids in the new `telegram_routes` table, so no `.env` change is needed. `/group_setup reset` recreates them, `/group_status` shows where things go.
- **Topics:** 📊 Daily report · 🗓 Weekly summary · 📅 Monthly summary · 🚨 Errors · 🤖 AI activity · 🔔 Alerts.
- **Routing is in one place** (`topic_for_alert` in `telegram/topics.py`, called from `create_and_send_alert`): `failure_cluster` -> Errors, `ai_action` -> AI activity, anything else -> Alerts, and any other **critical** alert -> Errors. Snooze still applies exactly as before.
- **Fallback:** if no group is configured, or a send to it fails (e.g. a topic was deleted), the message goes to DMs as before. Nothing is lost.
- **Reports** (`backend/reports/periodic.py`, plain text): daily 08:00 UTC, weekly Monday 08:10, monthly on the 1st at 08:15 (last 24h / 7d / 30d). Each shows wallets (total, active, not active by status, gas wallets, wallets that completed a task), tasks completed / failed / skipped and success rate, gas spent, most active projects, projects with most failures, top failure causes, open alerts, circuit breakers, and (daily) daily targets reached. Every number is a database query; the AI narrative (from `analyst.py`) is appended when available and the report goes out without it if AI is down.
- **AI activity digest** daily 08:05 UTC: autonomy frozen/active, autonomous actions in the last 24h with their `A<id>`, validations by type with average agreement, and how many validations/suggestions are waiting for you.
- `/report_now [daily|weekly|monthly|ai]` sends any report immediately.
- `send_telegram_message` now takes `topic=`, splits messages over 4000 characters, and retries as plain text if Telegram rejects the Markdown.

**Notes**
- Keep the group **private**: reports include aggregate numbers and AI action summaries with short wallet addresses.
- Only whitelisted user ids can run commands in the group; everyone else's messages are ignored.
- The old `send_daily_summary` in `alerts.py` is no longer scheduled (the new daily report replaces it); it can be deleted now or later, but dont forget to delete it.
- No frontend change in this phase.

**Migration:** none. `telegram_routes` is a new table created by `create_all()`.

**New/edited files in Phase 8**
- `backend/telegram/topics.py` — new
- `backend/telegram/group_commands.py` — new
- `backend/reports/periodic.py` — new
- `backend/telegram/sender.py` — replace
- Patched in place by `apply_phase8_patches.py`: `backend/main.py`, `backend/core/scheduler.py`, `backend/telegram/alerts.py`, `backend/telegram/bot.py`, `backend/telegram/commands/help.py`

## next up: phase 9

## Known, not built
**every times you discovered somethings usefull and you didn't build/fix it, add it here and the dev team will lock at it and build it, don't forgot to add recommendations if there is any here too:**
- Gas multipliers only go up; there is no decay back down after a quiet period.
- Wallets that reach the hard `cooldown` status (3 failures) are still never auto-recovered (pre-existing; the AI pause exists to avoid reaching it for systemic causes).
- `project_priority` reduces only; it does not restore priority when the project recovers.
- `SwapTask` uses `self.token_decimals` (18) for every input token, so token->token swaps of 6-decimal tokens (USDC/USDT) compute a wrong amount. Needs a decimals lookup before ERC20 swaps are trusted.
**added in Phase 7, with recommendations**
- **Claims page is dead**: `Claims.jsx` calls `/claims/eligible`, `/claims/pending`, `/claims/trigger`, `/claims/threshold`; no router serves them, and Telegram `/claim_trigger` only prints instructions. Nothing can execute a claim today. Recommend: Phase 9 builds read-only `/claims/*` on top of `claims/manager.scan_claimable_airdrops`, then a deliberate manual claim execution with a confirm dialog and dry-run support. Remove the stale auto-claim threshold box.
- **Project blacklist is unenforced**: `CompletedProjectsBlacklist` was only read by the removed discovery code. Recommend: either check it in project creation (route + Telegram wizard) or drop the table and command.
- **`DRY_RUN_MODE` env is ignored**: `kill_switch` starts with dry-run OFF regardless of config, and the dashboard toggle is in memory, so a restart goes live. Recommend: read `DRY_RUN_MODE` at startup and persist the toggle like the AI-autonomy flag.
- **Emergency stop is in memory too** and resets on restart; the agent loop is stopped by it but must be started again by hand. Recommend: persist it, and add an Agent start/stop control to the dashboard.
- **Faucets**: `method: GET` faucets are stored but every request is sent as POST; only `{address}` can be templated. `faucet/handlers/http_post.py` is unused and passes `proxies=`, which httpx >= 0.28 removed (delete it or use `client_proxy_kwargs`).
- **Proxies cover faucet claims only.** RPC calls and the transactions themselves still come from the server IP. Recommend: if Sybil-hardening matters, route RPC per wallet through its proxy (needs a per-wallet web3 provider). `Wallet.proxy_id` is an unused duplicate of `Proxy.wallet_id`.
- **Sessions**: login is not remembered across a page reload and the refresh-token endpoint is never used by the frontend. Recommend: use the refresh token (httpOnly cookie) so a reload or 30-minute expiry does not force a re-login, still keeping the access token out of localStorage.
- **`Sybil.jsx` health/Sybil scores** read `health_score`/`sybil_risk_score`, which `WalletResponse` does not return, so the grid shows "—" and 0. Recommend adding both fields to `WalletResponse`.
- **`Claims`, `Sybil`, `Snapshot`, `Notifications`** still use the old fetch + inline-style code instead of the shared `api` client and components (redesign scope, Phase 9).
- **Telegram wizard/`/projects` UI mismatch**: quick-add offers types (bridge, lending, dex) the wizard and prompts do not know.
- Gas multipliers only go up; no decay (Phase 6). Wallets that reach `cooldown` are still not auto-recovered (now manually recoverable from the Manage panel). `project_priority` only reduces.
- `SwapTask` decimals: fixed in the code (`_get_decimals` looks up the real token decimals) but the old "known, not fixed" note is still in §0.5; verify with a USDC test swap on testnet before trusting it.
**added in Phase 8**
Report times are fixed (UTC) in code; no dashboard control. Recommend a Settings card with report schedule + a "send test message to each topic" button.
Reports go to one group only; no per-topic mute. Telegram's own topic mute covers this for now.
If a topic is deleted in Telegram, sends fall back to DMs until /group_setup reset is run. Recommend auto-detecting "thread not found" and re-cre

## any suggestions or recommendations should be here(whethere new features, advices or whats ever it's) and there welcome.
- **Phase 9 should start from a short design system**: shared `Table`, `Modal`, `Toast`, `ConfirmButton` and `useApi` hook. Today every page re-implements loading, errors and confirm dialogs.
- **Audit log of manual actions** (who pressed Recover/Run now/Blacklist, when). The AI already has `ai_actions`; manual changes have none. Cheap to add and valuable once more than one person uses the panel.
- **Per-wallet "why am I not running?" view**: combine status, active hours, daily target, cooldown, nonce lock, proxy, gas balance into one explanation. The data all exists.
- **Backup reminder**: backups were removed by request, so show the database file size/age on the System panel and a banner if the file has not been copied for N days.
- **Task templates** (swap/bridge/stake presets that pre-fill fields) are the safe middle ground between "manual JSON" and AI-drafted task configs.


## Update cadence:
This file is updated/re-writed in bulk after each completed phase, not line-by-line during a phase(with short description of each phase).
This is the reference document for the Airdrop-Agent rebuild: what the system does today, what's being removed and why, what's being kept, what's being improved, what's being built new, and where the project is headed after that. Use this as the source of truth during the build.

---

## 1. What the project is
A self-hosted airdrop farming agent: manages HD/imported wallets across multiple EVM chains, runs configured on-chain tasks (swap/bridge/stake/liquidity/transfer) against registered projects on a schedule, tracks eligibility against manually-defined criteria, claims faucets and airdrops, and reports on all of it via a Telegram bot and a React dashboard. Backend is FastAPI + SQLAlchemy (async) + SQLite, frontend is Vite + React.

---

## 2. Current capabilities (as of this plan)

### Wallets
- Generate HD wallets from a master seed, or import raw private keys (encrypted at rest, AES via PBKDF2-derived key)
- Status lifecycle: active / paused / archived / blacklisted / cooldown
- Tagging and grouping
- Per-wallet "persona": active hours, sleep timing, gas multiplier, amount distribution, bidirectional-swap default, daily tx range
- Gas auto-refill via faucets when balance drops below a warning threshold
- Balance tracking (native + registered ERC20s) with USD valuation, refreshed on-demand or in bulk
- Health score and Sybil risk score per wallet

### Chains
- Register EVM chains with primary + fallback RPC URLs, automatic failover on connection
- Gas token config (native or ERC20), per-chain token registry (symbol → address/decimals)
- Gas price sampling (every 10 min) with 6-hour rolling average and spike detection (configurable multiplier)
- RPC latency testing, per-chain rate limiting

### Projects & tasks
- Projects: name, type (ecosystem/dapp), status, priority, max concurrent wallets, chain associations, notes, TGE/airdrop dates
- Task configs per project: swap, bridge, stake, unstake, provide/remove liquidity, transfer, generic contract interaction
- Amount ranges with weighted-random distribution (low/high/uniform), daily tx targets (min/max, randomized per wallet per day via seeded hash), task dependencies, bidirectional token pairs
- Eligibility criteria (manually or AI-extracted from docs): tx count, volume, time, governance, token-hold, social — tracked per wallet with a progress %

### Execution engine
- Fixed-slot worker pool with priority-weighted proportional queue fill (project.priority / total priority)
- Nonce locking with staleness recovery, gas-spike deferral, memory-pressure pause, contract-pause check
- Token approval flow (exact-amount, JIT, separate nonce) with human-like delay
- Transaction simulation (`eth_call`) before broadcast, dry-run mode (global toggle, checked at the actual broadcast chokepoint)
- Stuck-tx handling: auto speed-up (higher gas price) then auto-cancel, with a watchdog that detects and respawns frozen worker slots
- Per-project circuit breaker: auto-pauses after 5 consecutive failures, manually resettable

### Faucets
- Per-chain or per-project faucet registration with fallback URLs, cooldown periods, multi-token payouts
- Manual, threshold-triggered (checked every 30 min), and scheduled (every 24h) claiming

### Claims
- Scans registered claim contracts for claimable balances across active wallets
- USD-value estimate via price oracle
- **(Removed — see §3)** Auto-execution below a configurable threshold

### AI (Gemini primary + Groq validator, cross-checked)
- Dual validation for: risk assessment, ROI estimate, criteria extraction, config-change safety, gap analysis (task config vs criteria), Sybil correlation review
- Agreement scoring compares only structured decision fields (not prose), flags `requires_human` below 70% agreement
- Natural-language Telegram command router (Gemini primary, Groq fallback)
- **(Removed — see §3)** Discovery/scraping-based project finding, ROI estimation

### Sybil detection
- Correlates wallets by transaction timing proximity, task-sequence overlap, and gas-price reuse
- Feeds AI review on a scheduled interval

### Reporting
- Eligibility %, ROI *(removed)*, daily progress, gas usage, Sybil report, activity log, live server health (RAM/CPU/disk/worker slots), CSV export

### Auth & security
- JWT access + refresh tokens, TOTP 2FA with QR enrollment, device-trust cookies (skip 2FA on remembered devices), brute-force lockout (DB-persisted), IP whitelist middleware, encrypted seed/private-key storage
- **(Removed — see §3)** Encrypted nightly DB backup

### Interfaces
- Telegram bot: 150+ slash commands + natural-language fallback, confirmation flow for destructive actions
- React dashboard: wallets, balances, chains, tasks, projects, logs, reports, faucets, claims, Sybil risk, snapshot calendar, AI log, notifications, proxies (stub), settings (stub)
- WebSocket live log/status feed with HTTP polling fallback

### Alerts
- Telegram push for gas spikes, stuck tx, Sybil flags, claim thresholds, daily summary
- **(Removed — see §3)** New-project-found alerts (discovery is gone)

### Kill switch
- Emergency stop: halts new task dispatch and clears the queue; cannot un-broadcast an already-submitted transaction
- Global dry-run toggle enforced at the actual broadcast point, not just the queue-fill loop

---

## 3. Removals

Each item: what it is, why it's going, what (if anything) replaces it.

| # | Item | Why removed | Replacement |
|---|---|---|---|
| 1 | **Discovery/scraping system** — `backend/discovery/` (6 scrapers: DefiLlama, CryptoRank, airdrops.io, Twitter/Nitter, RootData, L2Beat), the aggregator, the processor, the 6-hourly scheduler job, `/ai/discovery/*` API routes, Telegram `discovery.*` commands, AI Log's "Discovery Status" dashboard card | Projects will be submitted manually only — by Musa via Telegram/website, and (per the beginner-friendly goal) potentially by other users via the website. No automatic source scraping anywhere, including the website. | Manual project submission flow (§5.5) |
| 2 | **AI ROI estimator** — `prompt_roi`, `get_roi_report`, `report_roi` (Telegram + dashboard) | No real market/funding data feeds it now that scraping is gone — it was already a rough LLM guess anchored to a handful of hardcoded historical airdrops. Kept it would mean showing confident-looking numbers with no basis. | None — dropped, not replaced |
| 3 | **Backup system** — `backend/security/backup.py`, the nightly `_run_backup` scheduler job, `system_backup` Telegram command | Explicit removal request. | None — user manages backups outside the app |
| 4 | **Auto-claim execution** — the auto-fire path inside `auto_claim_if_below_threshold`, `claim_set_threshold`, `claim_auto_on`, `claim_auto_off` | Explicit removal request: claiming is a fund-moving action and should always be a deliberate manual trigger. | Manual `claim_trigger` stays; claim scanning/tracking (`claim_check`, `claim_eligible`, `claim_pending`) stays as-is |
| 5 | **Telegram command surface** — cut from ~150 to ~45 commands (full before/after list in §4) | Most commands were config-heavy, rarely used on mobile, or duplicated what the dashboard already shows better as a table/form. | Cut commands' functionality moves to the website dashboard, which gets built out to cover them (see §5.5, §6) |

Also removed as direct consequences of the above:
- `DiscoveryRun` DB model and its dashboard usage
- Discovery-related imports/branches in `telegram/bot.py` and `telegram/commands/help.py`
- The dead/deprecated `backend/discovery/scheduler.py` (already unused, just deleting the corpse)

---

## 4. Telegram command surface: before → after

Approved curated set (~45 commands). Everything not listed here either moves to the website (still exists, just not as a Telegram command) or is deleted outright (discovery, ROI, backup, auto-claim toggles).

| Category | Kept in Telegram | Moved to website only |
|---|---|---|
| Wallet | `wallet_create`, `wallet_list`, `wallet_status`, `wallet_balance`, `wallet_pause`, `wallet_resume`, `wallet_blacklist`, `wallet_archive`, `wallet_tag`, `wallet_group`, `wallet_fund`, `wallet_health`, `wallet_sybil`, `wallet_top`, `wallet_failing`, `wallet_set_gas` | `wallet_unblacklist`, `wallet_unarchive`, `wallet_untag`, `wallet_cooldown`, `wallet_persona`, `wallet_nonce`, `wallet_gas_wallets` |
| Chain | `chain_list`, `chain_add`, `chain_enable`, `chain_disable`, `chain_status`, `chain_gas`, `chain_add_token`, `chain_tokens` | `chain_rpc`, `chain_add_fallback`, `chain_remove_fallback`, `chain_test_rpc`, `chain_gas_token`, `chain_set_rate_limit` |
| Task | `task_list`, `task_status`, `task_enable`, `task_pause`, `task_trigger` | `task_dry_run` (folds into global dry-run toggle), `task_deps`, `task_set_priority`, `task_trigger_all`, `task_template` |
| Project | `project_list`, `project_add`, `project_status`, `project_enable`, `project_disable`, `project_pause`, `project_resume`, `project_approve`, `project_reject`, `project_gap`, `project_reset_circuit` | `project_farm` (dup of enable), `project_prioritize`, `project_cap`, `project_update`, `project_criteria`, `project_blacklist`, `project_circuit_breaker` |
| Agent | `agent_status`, `agent_start`, `agent_stop`, `agent_pause_all`, `agent_resume_all`, `agent_unlock` | `agent_workers`, `agent_queue` (dashboard live views) |
| Report | `report_eligibility`, `report_daily_progress`, `report_gas`, `report_server` | `report_sybil`, `report_activity` (dashboard does these better) — `report_roi` deleted |
| Faucet | `faucet_request`, `faucet_bulk` | `faucet_list`, faucet CRUD (website) |
| Claim | `claim_check`, `claim_eligible`, `claim_trigger`, `claim_pending` | `claim_history` (website) — `claim_value` folds into `claim_pending`; `claim_set_threshold`/`claim_auto_on`/`claim_auto_off` deleted (auto-claim removed) |
| Config | `config_show`, `config_set` | `config_reset` (destructive — safer with a confirm dialog on web) |
| AI | `ai_status`, `ai_pending`, `ai_approve`, `ai_reject`, `ai_autonomy_off`, `ai_autonomy_on` | `ai_log`, `ai_validate`, `ai_agreement` (website AI Log page) |
| Nonce | `nonce_release_all` (emergency only) | `nonce_check`, `nonce_sync`, `nonce_release` |
| TX | `tx_stuck`, `tx_speedup`, `tx_cancel` | `tx_status`, `tx_failed`, `tx_verify` |
| Gas | `gas_price`, `gas_refill` | `gas_spike`, `gas_optimal`, `gas_cost`, `gas_budget`, `gas_history` |
| Alert | `alert_list`, `alert_resolve_all` | `alert_snooze`, `alert_unsnooze`, `alert_test`, `alert_resolve`, `alert_memory` |
| System | `system_status`, `system_version` | `system_test_rpc`, `system_maintenance`, `system_maintenance_off`, `system_log_archive` — `system_backup` deleted |
| Schedule | — (cut entirely) | folds into `task_list` / website |
| Proxy | — (cut entirely from Telegram) | website (already marked "coming soon" in `Proxies.jsx`) |
| Discovery | — (all deleted) | n/a — feature removed |

Net effect: Telegram becomes the **quick-action remote** (status checks, pause/resume, emergency stops, approvals). The website becomes the **real control panel** for configuration-heavy or destructive actions.

---

## 5. New features (build now)

### 5.1 Improved natural-language command handling
**Current state:** `nl_parser.py` routes free text through Gemini (Groq fallback) into a fixed action+params JSON, matched against a large `if/elif` chain in `bot.py`.
**Problems to fix:**
- The action list the LLM must choose from will shrink significantly (§4), which should *improve* accuracy — fewer, clearer choices
- No conversation memory — every message is parsed cold, so a follow-up like "make it 10" after "add project X" has no context
- No entity resolution — if the user says "pause my main wallet" there's no fuzzy-match against wallet tags/names, only exact IDs
**Plan:**
- Keep the Gemini-primary/Groq-fallback structure, update the action list/prompt to match the curated command set
- Add short-lived conversation context (last 1–2 turns) so follow-up messages can complete a partial command
- Add fuzzy entity resolution for wallet/project references by tag or name, not just numeric ID
- Clearer error messages when parsing fails or confidence is low, instead of a generic "AI unavailable"

### 5.2 Improved AI analyst/reporting
**Current state:** Reports are raw data dumps (JSON or plain text lines). No synthesis, no "here's what changed" framing.
**Plan:**
- A daily/on-demand AI-written summary layer on top of existing reports (eligibility, gas, activity) — plain-language interpretation, not just numbers: "3 wallets fell behind their daily target on Project X, likely due to a gas spike at 14:00 UTC"
- Trend detection: flag when a metric moves outside its recent normal range (e.g., failure rate spike, gas cost spike) rather than requiring Musa to notice it in a table
- This reuses the existing `dual_ai_validate` infrastructure with a new `task_type="analyst_summary"` prompt — no new AI plumbing needed

### 5.3 AI-managed tasks and wallets (fully autonomous, with guardrails)
**Environment: testnet only, not mainnet.** This lowers the stakes considerably — no real funds at risk — but guardrails are still worth keeping, mainly so a bad AI decision can't spam pointless transactions, burn through faucet cooldowns, or mask a real bug behind constant auto-correction. The limits below are sized for testnet (looser than a mainnet deployment would ever get).

**Confirmed scope:** fully autonomous — AI can enable/disable tasks, adjust wallet settings, and manage the queue on its own.

**Guardrails:**
- **Hard boundary — never autonomous:** AI cannot add a new project, add a new task config from scratch, change a wallet's private key/seed handling, or touch claim execution. Autonomy is scoped to *pausing/resuming/tuning what already exists*, not creating new surfaces. (This stays even on testnet — it's about preventing runaway/nonsensical behavior, not fund safety.)
- **Every autonomous action is logged** with the reasoning that triggered it (extends `AIValidation`/`Log` — a new `ai_actions` table: what changed, why, timestamp, reversible-or-not)
- **Every autonomous action is reversible** — pausing a task/wallet, not deleting it; adjusting `WalletSettings` fields like gas multiplier or daily tx range within pre-set safe bounds, not arbitrary values
- **Telegram notification on every autonomous action** (ties into §5.4) — Musa sees it happen in near-real-time, doesn't have to go looking
- **A rate limit on autonomous changes** per wallet/project per day, so a bad AI decision can't cascade — set at **10 autonomous adjustments per wallet per 24h** (loose, testnet-appropriate; tighten later if it moves to mainnet)
- **An off switch** — one Telegram command / dashboard toggle to freeze all AI autonomy instantly, independent of the existing kill switch (which stops the whole agent, not just AI decisions)

**Concrete behaviors to build:**
- Auto-pause a wallet after N consecutive task failures *before* it hits the existing hard-coded 3-failure cooldown, if the AI's error analysis (§5.4) identifies a systemic cause (e.g. gas token depleted, RPC degraded) rather than a one-off
- Auto-adjust a wallet's gas multiplier within safe bounds if it's consistently failing on gas price alone
- Auto-disable a task config the gap analysis (`project.gap`, already kept) flags as unsupported by the project — this already exists for the *safe reversible half* per the existing code comment; extend the same pattern to more cases
- Queue prioritization suggestions — not silent reordering, but AI can recommend and (if approved as autonomous) apply a priority reshuffle when a project's circuit breaker keeps tripping

**This needs a decision round before implementation — see Open Questions (§7).**

### 5.4 AI error notification/reporting
**Current state:** Errors go to logs and, for some categories, to Telegram via `create_and_send_alert`. No AI synthesis — you get the raw exception string.
**Plan:**
- Route failure clusters (not every single failure — that's alert spam) through an AI summarization pass: "5 tasks failed on Chain X in the last hour, all with 'insufficient gas' — likely the faucet is failing or gas price spiked"
- Distinguish transient (retry-worthy) from systemic (needs human attention) failures using the existing gas-spike/circuit-breaker signals as input to the AI's classification
- This is the same underlying mechanism as §5.3's failure detection — they should share one "failure analysis" AI call rather than duplicating logic

### 5.5 Beginner-friendly manual project add (Telegram + website)
**Current state:** `project_add` only takes name + type; task configs, criteria, and contracts are added via separate raw commands or direct API calls with many required JSON fields (see `TaskConfigCreate`, `ProjectCriteria` schemas) — not friendly to a non-technical user.
**Plan — Telegram:**
- Turn `project_add` into a guided multi-step conversation (using the existing confirmation-flow pattern already in `bot.py`) instead of a single command with positional args: name → type → chain → website/socials → "add a task now?" (walks through task type, amounts, contract address with inline help text) → "add criteria now?" (optional, can be added later via AI extraction from docs if the project has a docs URL)
**Plan — website:**
- A step-by-step "Add Project" wizard on the dashboard (this becomes the primary path once cut commands move here per §4) — form-based, with inline validation (e.g. checksum-validate addresses before submit, warn on missing gas token config for the selected chain)
- Reuse the existing `dual_ai_validate` criteria-extraction prompt as an *optional* "paste your project's docs URL and I'll draft criteria for you to review" step — draft only, never auto-applied without the human clicking accept (consistent with the "AI never auto-creates" boundary in §5.3)

---

## 6. Improvements to existing, kept features

These aren't new features or removals — they're fixes/polish to things staying in the system.

- **Sybil re-score scheduling:** change from fixed `IntervalTrigger(hours=12)` to a self-rescheduling job with a randomized 6–18h delay each cycle
- **AI validation scope narrows:** `dual_ai_validate` for risk/config/criteria/gap now runs only against manually-submitted projects — same code path, different (and simpler) trigger context now that there's no scraped-candidate firehose feeding it
- **Website dashboard build-out:** absorbs the ~105 cut Telegram commands' functionality as proper forms/tables (chain RPC management, task templates/dependencies, project criteria editor, config reset with confirm dialog, gas budget/history views, alert snooze, proxy management — currently a stub page) — this is a substantial frontend scope on its own, likely its own phase
- **`Proxies.jsx`** currently says "coming soon" — becomes real once proxy commands move here from Telegram

---

## 7. Open questions — resolved

1. ~~Rate limit numbers~~ — **settled:** 10 autonomous adjustments per wallet per 24h (testnet-appropriate)
2. **Safe bounds for auto-adjustment** — **settled:** the AI may move `WalletSettings.gas_multiplier` within a 0.7×–1.8× floor/ceiling, and by no more than ±0.1 in any single adjustment (on top of the existing ±5% random variation already applied at broadcast time). Wide enough to fix a systematically-underpriced wallet, narrow enough that one bad AI call can't swing a wallet's gas spend drastically in one step. Other `WalletSettings` fields the AI may touch (daily tx range, active hours) get the same "small step, hard floor/ceiling" pattern when implemented — exact bounds for those to be set per-field during Phase 6 build, following this same principle.
3. **The AI autonomy off-switch** — **settled:** both Telegram and dashboard, backed by one shared backend flag — same pattern as the existing `is_emergency_stop()` / `is_dry_run()` getters in `kill_switch.py` (e.g. `is_ai_autonomy_paused()`). Telegram needs it because that's where autonomous-action notifications land (§5.4) — if something looks wrong, the kill switch should be reachable from the same screen. Dashboard needs it because Settings is where every other operational toggle already lives. Both read/write the same flag; no duplicated logic.
4. **Approval threshold reuse** — **settled:** reuse the existing 70% Gemini/Groq agreement gate from `dual_ai_validate` rather than building a second threshold system. Below 70% agreement, the action becomes a notify-and-wait suggestion instead of an autonomous action — consistent with how every other AI decision in the system already behaves.

---

## 8. Future roadmap — suggestions for later (not in current scope)

Ideas worth considering after the current phase, not committed to yet:

- **Multi-user support** — currently single-operator (one whitelisted Telegram ID set, one admin login). If the website's beginner-friendly project-add is meant for others too, the system likely needs real user accounts/roles eventually, not just IP + password + TOTP for one operator.
- **Webhook-based faucet/claim triggers** instead of polling — `webhooks.py` already exists as a stub registry but nothing calls `dispatch_event`; wiring it up could let external services (a project's own notification bot, a claim-live announcement) push events in instead of the agent polling every 30 min.
- **Per-project custom ABI storage** — `ProjectContract.abi_fragment` exists in the schema but generic task types (`generic.py`) still take raw hex `data` from config; a small ABI-aware builder would make manual project setup much friendlier, tying directly into §5.5.
- **Historical gas-cost vs actual-received tracking** — now that ROI estimation (AI-guessed) is gone, a *factual* ROI view (gas spent vs tokens actually received, once claims are confirmed) would be genuinely useful and requires no AI guessing — just linking `claim_trigger` results back to `gas_cost_usd` per project.
- **Mobile push notifications beyond Telegram** — if the website is meant for broader use, Telegram-only alerts limit it to Musa; a simple in-app notification center already exists (`Notifications.jsx`) and could gain a browser-push or email fallback.
- **Mainnet readiness pass (if ever needed)** — the project runs testnet-only for now, which is why §5.3's guardrails are set loose. If mainnet ever comes into scope later, everything in §5.3 needs a second pass first: tighter rate limits, a stricter agreement-score gate, and probably a required-human-approval mode as the default rather than an option.
- **Rate-limit / cooldown visualization** — a single dashboard view showing every wallet's current cooldown/active-hours/daily-target state at a glance, since this data exists (`WalletSettings`, `TaskDailyProgress`) but is currently only visible per-wallet on request.
- **Real-time AIs analysis & improvements & validation & reports/alerts and so on/etc**
- **and a lots of featurs thats i for forgot to mentions & your allowed to suggest for new features thats you find is useful for this project, including now or for the future roadmap, thank you**
- if you get some too while lookimg/viewing this project you are good/allowed to add some too, if there useful just add them and explain, thats all.
---

## 9. Execution phases (proposed grouping — for reference once building starts)

1. **Phase 1 — Removals:** discovery system, ROI estimator, backup system, auto-claim execution, Telegram command trim. *built*
2. **Phase 2 — Kept-feature improvements:** Sybil re-score randomized interval, AI validation scope narrowing. *built*
3. **Phase 3 — New feature: manual project add** (§5.5) — Telegram guided flow + website wizard. **and i have forgot to a remove & edit projects in the project tab** - we need to add this when building **phase 4** edit/remove project in project tab. *built*
4. **Phase 4 — New feature: NL improvements + AI analyst/reporting** (§5.1, §5.2). *built*
5. **Phase 5 — New feature: AI error notification** (§5.4) — shares logic with Phase 6. *built*
6. **Phase 6 — New feature: AI-managed tasks/wallets** *built*
7. **Phase 7 — Website build-out** for everything moved off Telegram (§4, §6) & website improvement including redesign, better ui/ux an a lots more. *built*
8. **Phase 8 - Telegram channel/group - with topic** including daily report, errors, summary of project works(daily, weekly, monthly)(each different topic), ai report(including all it activities(need validation, etc), total wallets active/non-active with total task/tnx completed/faild, and the remaining thats i forgot to mention and you have right to suggest for improvement or not to add something here, your always welcome. *not yet*
9. **Phase 9 - Website redesign** Full redesign + remaining polish(both android & desktop mode). *not yet*
10. **Phase 10 - Documentations** including README.md, ROADMAP.md, docs, Architecture.md, How-its-works.md, security.md and the rest/a lot more  of the valueble documments. *not yet*

This grouping is a suggestion, not a commitment — order can change based on what MusaAis wants tackled first once execution begins.
