# How it works

## 1. From project to transaction
1. **Add a project** (website wizard or Telegram wizard): details, chains, socials, a task config, then optional criteria (AI can *draft* criteria from a docs URL; a human must accept).
2. Every 30 s `fill_queue` takes active projects (not paused/stopped/archived, circuit breaker off, eligibility not declared) and splits free worker slots by `priority / total_priority`, capped by `max_concurrent_wallets`.
3. For each project, candidate (wallet, task) pairs are filtered: wallet active and not a gas wallet; HD wallets excluded while the seed is locked; inside the wallet's active hours **and past its personal start offset** for the day; **past its sleep time** (`Wallet.next_available_at`); no active task for that wallet/chain; **the task itself is due** (`TaskSchedule.next_run_at`); chain enabled; daily target not reached; dependency tasks completed today. Each wallet contributes one candidate per cycle (a random one of its due tasks), and one task per wallet across all projects in a fill. Least-recently-selected wallets sort first (`last_selected_at` is written when a wallet is selected).
4. A free worker slot runs `BaseTask.execute()`. When it ends, the outcome sets the pacing below.

### Pacing (human-like behaviour, `core/scheduling.py`)
| After | Same wallet+task is due again after | Wallet is idle for |
|---|---|---|
| success | `frequency_mins` x U(0.8, 1.4) | `sleep_min_mins`..`sleep_max_mins` (persona/settings) |
| failed / timeout | about 10 min x U(0.8, 1.5) | same |
| skipped (gas spike, low gas, paused contract, memory pressure) | U(3, 8) min | same |
| simulated (dry-run) | not recorded | not recorded |

After the active window opens, each wallet waits a personal, deterministic offset in `[0, start_offset_max_mins]` (different per wallet and per day) before its first task, so wallets that share a window don't all fire in the first cycle. Consequence: with `frequency_mins=120` and a 12 h window a wallet completes roughly 5-6 tasks a day, so keep `daily_tx_min/max` and `frequency_mins` consistent or targets will read as unmet. Manual triggers are not paced and do not move the schedule.

## 2. The execution pipeline (`tasks/base.py`)
1. Connect to chain (RPC pool, fallbacks).
2. **Gas-spike guard**: current price vs 6 h average; defer if spiking.
3. Estimate gas, convert to gas-token units, require balance >= estimate x 1.2, else skip as `low_gas`.
4. Contract-paused check (if supported).
5. Lock the wallet+chain nonce; it is raised to the chain's `pending` count if the stored value is behind.
6. Build tx params. If a token approval is needed it is sent as its own transaction (exact amount, human-like delay) and the main tx is rebuilt with a fresh nonce.
7. Simulate with `eth_call`; abort on revert.
8. Apply the wallet's gas-multiplier variance.
9. **Dry-run gate**: if dry-run is on, release the nonce, write a `simulated` log row and stop. In dry-run, approvals are also not sent.
10. Sign (HD key derived from the in-memory seed, or imported key decrypted with `MASTER_PASSWORD`), broadcast, record a `pending` transaction, release the nonce, wait for the receipt (stuck handler speeds up, then cancels).
11. **Fee recording**: from the receipt, `gas_used`, `gas_token`, `gas_cost_native` (fee actually paid, in gas-token units) and `gas_cost_usd` (native x CoinGecko price) are stored on the transaction. This also runs for reverted transactions, which still burn gas. A price-lookup failure leaves only the USD estimate empty. Failed transactions also store an `error_message`.

### Outcomes and their effects
| Outcome | Wallet failure count | Project circuit breaker | Notes |
|---|---|---|---|
| success | unchanged | reset | daily progress +1, `Log` row (with gas cost) |
| failed | +1 (cooldown at 3) | +1 (trips at 5) | classified, stored in `task_failures` |
| skipped (gas spike, low gas, paused contract) | unchanged | unchanged | throttled record in `task_failures` |
| simulated (dry-run) | unchanged | unchanged | |
| timeout (480 s) / exception | +1 | +1 | |

## 3. Safety switches
| Switch | Scope | Persistence |
|---|---|---|
| Emergency stop (`/agent_kill`, `/agent_pause_all`, `POST /agent/kill`) | halts dispatch, clears queue, stops loop; cannot un-broadcast a sent tx | **persisted** (`kill_switch_state`); stays on after a restart until cleared (dashboard "Clear emergency stop" or `/agent_resume_all`) |
| Dry-run | simulate everything, broadcast nothing; also pauses automatic queue filling | **persisted**. `DRY_RUN_MODE=true` in `.env` additionally forces it ON at every boot (it can never force it off) |
| AI-autonomy freeze | stops only AI-made changes | persisted in `ai_autonomy_state` |
| Agent stop (`/agent_stop`, `POST /agent/stop`) | stops the loop only, no emergency | not persisted: the loop starts again at boot |
| Maintenance window command | not enforced by the scheduler | n/a |

At startup the saved emergency-stop and dry-run state is restored **before** the scheduler and agent loop start. If that state cannot be read, the agent starts in emergency stop + dry-run (fail safe). A restart with the emergency stop active leaves the agent idle; clear it and start the agent. To run live permanently set `DRY_RUN_MODE=false` and switch dry-run off in the dashboard (that choice is saved).

## 4. AI behaviour
- **Gemini** (primary) and **Groq** (validator) run concurrently. Only decision fields (`status`, `recommendation`, `approved`, `kyc_required`, confidence bucket, `risk_level`) are compared. Agreement >= 70% proceeds; below that, or if Groq is unavailable, the result is flagged for a human.
- **Failure analysis** (every 10 min): a deterministic classifier groups failures; a cluster is 3+ events, same category, same chain, within 60 min. Transient clusters give an info alert; systemic clusters give a warning (critical at 10+ events or 5+ wallets) with an AI-narrated cause. The AI only narrates verified facts.
- **Autonomy** (every 10 min): code proposes, AI vetoes.

| Action | Trigger | Bounds |
|---|---|---|
| `wallet_pause` | 2+ consecutive failures in a systemic low_gas/rpc/nonce cluster | auto-resumes when the cause clears; gas wallets never paused |
| `gas_multiplier` | 2+ "underpriced" rejections | +0.1 per step, range 0.7-1.8 |
| `task_disable` | 3+ task-level failures (config errors, or reverts across 2+ wallets) | reversible |
| `project_priority` | 10+ project-attributable failures across 2+ wallets in 24 h | -1, minimum 1 |

Guardrails: max 10 adjustments per target per 24 h; max 5 AI reviews per cycle; per-type cooldowns; 12 h cooldown after a human undo; suggestions expire after 24 h; bounds re-checked against live state at apply time. Never autonomous: adding projects or task configs, key/seed handling, claims, deleting anything.
- Below 70% agreement, an action becomes a **suggestion** (`/ai_approve A<id>`, `/ai_reject A<id>`).
- AI-written report summaries narrate numbers computed in Python; the AI does not compute figures.

## 5. Telegram
- Slash commands are the quick-action remote (status, pause/resume, approvals, kill). Free text goes through the NL parser (Gemini, Groq fallback) with last-2-turns memory and fuzzy wallet/project resolution. Ambiguous matches ask instead of guessing.
- Destructive commands stage a confirmation: reply `confirm` (valid 60 s) or `cancel`.
- Only user ids in `TELEGRAM_ALLOWED_USER_IDS` can command the bot.
- `agent.unlock` and `wallet.import` are forbidden through NL because they carry secrets.
- Run `/group_setup` inside a private supergroup with Topics to create: Daily, Weekly, Monthly, Errors, AI activity, Alerts. If a send fails, messages fall back to DMs.

## 6. Reports
Daily (08:00 UTC), weekly (Mon 08:10), monthly (1st 08:15) cover wallets, tasks completed/failed/skipped, success rate, gas spent, top projects, top failure causes, open alerts and circuit breakers.

**Gas figures** are reported in each chain's own gas token, per token, never summed across tokens: for example `0.0035 ETH · 0.0004 BNB`. This covers the dashboard overview (24h / 7d / all-time and per project), the daily/weekly/monthly reports, `/report_gas`, `/report_weekly`, gas per wallet, wallet compare, the daily-summary alert and the AI analyst (whose gas-spike flag also works per token). "Gas spent" includes reverted transactions (they burn gas) and does not include transactions recorded before fee tracking existed. API payloads still carry `gas_usd`, but that is an estimate (a testnet token priced at its mainnet value, empty if CoinGecko fails) and is no longer used in any report text.

## 7. Eligibility
Per-wallet progress comes from criteria (tx count, volume, time, governance, token-hold, social). Two implementations exist (`reports/eligibility.py` and `projects/eligibility.py`) and they can disagree; volume uses `gas_cost_usd` as a proxy (an estimate, empty when the price lookup fails). Treat percentages as indicative. Declaring a project eligible or not-eligible (website only) permanently stops new tasks for it.
