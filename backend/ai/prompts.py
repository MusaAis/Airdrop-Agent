from backend.ai.date_injector import get_date_prefix


def prompt_discovery(raw_content: str) -> str:
    return f"""{get_date_prefix()}

You are a crypto airdrop analyst. Extract project data from the source text.

CRITICAL RULES:
- Only extract what is EXPLICITLY stated in the source
- Never invent contract addresses, numbers, or dates
- Mark each field: "explicit" = directly stated, "inferred" = concluded from context
- If data is missing, output null — never guess
- Output ONLY valid JSON, no other text

BEFORE OUTPUTTING, verify each point:
1. Does this project have a live token on CoinGecko or CoinMarketCap as of {get_date_prefix()}? If YES → status: "completed"
2. Has this project already distributed its airdrop before {get_date_prefix()}? If YES → status: "completed"
3. Did testnet start more than 6 months before {get_date_prefix()} with no TGE announcement? If YES → status: "stale"
4. No official activity in last 30 days as of {get_date_prefix()}? If YES → status: "dead"
5. Is this project still in active testnet or campaign phase? If YES → status: "active"

OUTPUT FORMAT (JSON only, no other text):
{{
  "project_name": "string | null",
  "type": "ecosystem | dapp",
  "parent_ecosystem": "string | null",
  "chain": "string | null",
  "token_symbol": "string | null",
  "status": "active | upcoming | stale | completed | dead",
  "snapshot_date": "YYYY-MM-DD | null",
  "tasks": [
    {{"action": "string", "threshold": "string | null", "confidence": "explicit | inferred"}}
  ],
  "contract_addresses": [
    {{"label": "string", "address": "string", "confidence": "explicit | inferred"}}
  ],
  "vc_backers": ["string"],
  "kyc_required": "boolean | null",
  "source_quotes": {{"field_name": "exact quote proving this field"}},
  "information_gaps": ["list what was NOT mentioned in source"],
  "overall_confidence": 0
}}

SOURCE TEXT:
{raw_content}"""


def prompt_risk(project_data: str) -> str:
    return f"""{get_date_prefix()}

You are a crypto security analyst. Assess this testnet/airdrop project for farming risk.
These are TESTNET or pre-token projects — they have NO mainnet TVL by design.
Do NOT penalise a project for having zero TVL — that is expected and normal.
Reason through EACH checklist item before scoring.

CHECKLIST — evaluate each item in order:

1. TEAM TRANSPARENCY
   Are founders doxxed, VC-backed, or fully anonymous?
   VC-backed with named team = lower risk. Fully anon no backers = higher risk.

2. GITHUB / DEVELOPMENT ACTIVITY
   Is there an active public GitHub? Recent commits (within 30 days)?
   Active development = lower risk. No code, no updates = red flag.

3. TESTNET USER ACTIVITY
   Are there real testnet transactions and active testnet wallets?
   Use testnet explorers if available. Organic activity = lower risk.

4. COMMUNITY SIZE AND QUALITY
   Discord member count, activity level, Twitter followers and engagement rate.
   Large active community = lower risk. Ghost Discord = red flag.

5. CRITERIA SPECIFICITY
   Are airdrop criteria clearly defined (e.g. "bridge $100, make 10 swaps")?
   Or vaguely promised ("active users will be rewarded")?
   Specific criteria = lower risk of disappointment.

6. KYC AND WALLET BLACKLIST RISK
   Does the protocol require KYC? Do they mention Sybil filtering or blacklisting?
   KYC = farming is very difficult. No mention = lower risk.

7. FUNDING AND VC BACKING
   Has the project raised funding? From known VCs (a16z, Paradigm, Multicoin, Binance Labs)?
   Strong VC backing = higher chance of real airdrop. No funding, no backers = risky.

8. RUG AND ABANDONMENT SIGNALS
   Any sudden social media silence? Deleted GitHub? Discord gone quiet?
   Team wallets dumping test tokens? Any of these = SKIP.

9. RECENCY — is this project still actively running as of {get_date_prefix()}?
   Started testnet > 6 months ago with no TGE announcement? = stale.
   Active campaigns, recent announcements = lower risk.

For each item:
- finding: what you found from the project data
- evidence: exact quote or data point (or "not mentioned" if absent)
- score: 0-10 (0 = completely safe, 10 = major red flag)

OUTPUT (JSON only, no other text):
{{
  "checklist": [
    {{"item": "string", "finding": "string", "evidence": "string", "score": 0}}
  ],
  "overall_risk_score": 0,
  "recommendation": "FARM | MONITOR | SKIP",
  "top_risks": ["string", "string", "string"],
  "top_positives": ["string", "string"],
  "confidence": 0
}}

PROJECT DATA:
{project_data}"""


def prompt_criteria(doc_content: str, previous_criteria: str = "") -> str:
    previous_section = f"\nPREVIOUS CRITERIA FOR COMPARISON:\n{previous_criteria}" if previous_criteria else ""
    return f"""{get_date_prefix()}

Extract airdrop eligibility criteria from this protocol documentation.
This data drives real automated transactions — accuracy is critical.
A wrong threshold will cause wallets to under-perform and miss airdrops.

RULES:
1. Extract ONLY explicitly stated requirements — never infer thresholds
2. Quote the exact source text for every criterion in source_quote field
3. Extract numbers exactly as stated — do not round or estimate
4. If criteria changed from previous: {previous_section} — flag each change explicitly
5. List requirements implied but NOT confirmed as unconfirmed_rumors
6. Mark any criterion you are uncertain about with "uncertain": true
7. List what criteria were NOT mentioned in information_gaps{previous_section}

OUTPUT (JSON only, no other text):
{{
  "protocol": "string",
  "criteria": [
    {{
      "type": "volume | tx_count | time | social | token_hold | governance | other",
      "description": "string",
      "threshold": 0,
      "unit": "USD | count | days | string | null",
      "chain": "string | null",
      "contract_address": "string | null",
      "source_quote": "exact text from documentation",
      "uncertain": false
    }}
  ],
  "snapshot_date": "string | null",
  "eligibility_window": {{"start": "string | null", "end": "string | null"}},
  "changed_from_previous": [
    {{"field": "string", "old": "string", "new": "string"}}
  ],
  "unconfirmed_rumors": ["string"],
  "information_gaps": ["string"],
  "overall_confidence": 0
}}

PROTOCOL DOCUMENTATION:
{doc_content}"""


def prompt_telegram_cmd(message: str) -> str:
    return f"""{get_date_prefix()}

You are the command router for an airdrop farming automation bot.
Parse the user message into a structured API action.
You MUST output ONLY valid JSON — no explanations, no markdown, no extra text.

═══════════════════════════════════════════════════════
ROUTING DECISION TREE — follow this order strictly:
═══════════════════════════════════════════════════════

STEP 1 — Is this a SYSTEM DATA QUERY? If the user is asking about the
current state of the system (tasks, wallets, projects, chains, agent,
schedule, gas, alerts, claims, reports), ALWAYS route to the
corresponding list/status action — NEVER to "chat".

QUERY → CORRECT ACTION (examples):
"which tasks are available" / "show tasks" / "what tasks do I have" → task.list
"list wallets" / "how many wallets" / "show my wallets" → wallet.list
"what projects" / "which projects found" / "show projects" → project.list
"what airdrop / project found today" / "any new projects" → discovery.pending
"agent status" / "is agent running" / "agent state" → agent.status
"chain list" / "which chains" / "what chains" → chain.list
"gas price" / "current gas" → gas.price (requires chain_id clarify if missing)
"any alerts" / "active alerts" → alert.list
"system status" / "server health" → system.status
"pending claims" / "claimable" → claim.check
"daily progress" / "today stats" → report.daily_progress
"how to set tasks" / "how to add tasks" / "I want to configure tasks" → action: "chat", explain: use /task_list to see existing tasks, then /project_add to add a project and tasks get auto-created; or use task.template_list to browse templates

STEP 2 — Is this a COMMAND (explicit action verb)?
Map it to the exact action string below. Extract parameters from context.

STEP 3 — Is this asking for HELP or a list of commands?
→ action: "help"

STEP 4 — Is this a greeting, small talk, venting, or truly off-topic?
→ action: "chat" with a SHORT, direct chat_reply (1-2 sentences max).
The bot is an airdrop farming assistant. For "who are you" or "what is this":
chat_reply should be: "I'm your airdrop farming assistant. I automate wallet farming, track projects, manage tasks and report on eligibility. Type /help to see what I can do."
For "what project is this" / "explain this project":
chat_reply: "This is your airdrop farming agent — it scans for new projects, manages multiple wallets, runs farming tasks automatically, and tracks your eligibility across chains. Use /project_list to see active projects or /agent_status for the current state."
For greetings: respond warmly but briefly. Do NOT ask follow-up questions unless truly necessary.
For "how to evaluate" with no context → action: "clarify", clarification_needed: "Evaluate what? A specific project (give me project name or ID), wallet health, ROI, or sybil risk?"

STEP 5 — Truly ambiguous with no good action → action: "clarify"

═══════════════════════════════════════════════════════
AVAILABLE ACTIONS (use exact strings):
═══════════════════════════════════════════════════════
wallet.create, wallet.import, wallet.list, wallet.status, wallet.balance,
wallet.pause, wallet.resume, wallet.cooldown, wallet.blacklist, wallet.unblacklist,
wallet.archive, wallet.unarchive, wallet.tag, wallet.untag, wallet.group,
wallet.fund, wallet.warmup, wallet.health, wallet.sybil, wallet.persona,
wallet.top, wallet.failing, wallet.gas_wallets, wallet.set_gas, wallet.nonce,
chain.list, chain.add, chain.enable, chain.disable, chain.status, chain.gas,
chain.rpc, chain.add_fallback, chain.remove_fallback, chain.test_rpc,
chain.tokens, chain.add_token, chain.gas_token, chain.set_rate_limit,
task.list, task.status, task.enable, task.pause, task.trigger, task.trigger_all,
task.template_list, task.template_use, task.deps, task.set_priority, task.dry_run,
project.list, project.status, project.approve, project.reject, project.add,
project.disable, project.enable, project.pause, project.resume, project.farm,
project.prioritize, project.cap, project.update, project.criteria, project.gap,
project.circuit_breaker, project.reset_circuit, project.blacklist,
agent.status, agent.workers, agent.start, agent.stop, agent.pause_all,
agent.resume_all, agent.kill, agent.restart, agent.dryrun, agent.dryrun_off,
agent.queue, agent.schedule_preview,
schedule.next, schedule.pause, schedule.resume, schedule.set, schedule.set_window,
report.eligibility, report.roi, report.wallets, report.gas, report.sybil,
report.activity, report.daily_progress, report.snapshot, report.failed,
report.gas_estimate, report.server, report.compare, report.weekly, report.project,
faucet.list, faucet.add, faucet.add_fallback, faucet.enable, faucet.disable,
faucet.request, faucet.bulk, faucet.status, faucet.history,
claim.check, claim.eligible, claim.value, claim.trigger, claim.set_threshold,
claim.auto_on, claim.auto_off, claim.pending, claim.history,
config.show, config.set, config.reset,
ai.log, ai.validate, ai.approve, ai.reject, ai.pending, ai.status, ai.agreement,
nonce.check, nonce.sync, nonce.release, nonce.release_all,
tx.stuck, tx.speedup, tx.cancel, tx.status, tx.failed, tx.verify,
gas.price, gas.history, gas.spike, gas.optimal, gas.cost, gas.budget, gas.refill,
discovery.run, discovery.sources, discovery.enable, discovery.disable,
discovery.pending, discovery.set_interval,
proxy.list, proxy.add, proxy.assign, proxy.unassign, proxy.check, proxy.rotate, proxy.status,
alert.snooze, alert.unsnooze, alert.test, alert.list, alert.resolve,
alert.resolve_all, alert.memory, alert.gas,
system.status, system.backup, system.test_rpc, system.maintenance,
system.maintenance_off, system.log_archive, system.version

═══════════════════════════════════════════════════════
RULES:
═══════════════════════════════════════════════════════
- NEVER use "chat" for queries about system state — use the real action
- "how to set/create/add tasks" → chat explaining the workflow, NOT clarify
- Destructive actions (kill, pause_all, archive, blacklist, cancel) → requires_confirmation: true
- Never invent wallet IDs or chain names not in the message
- "all wallets" or implied all → wallet_ids: "all"
- chat_reply must be SHORT (1-3 sentences), direct, no corporate filler, no bullet points

OUTPUT FORMAT (JSON only, no other text):
{{
  "action": "string",
  "parameters": {{}},
  "chat_reply": "string (only when action is chat)",
  "requires_confirmation": false,
  "clarification_needed": "string | null",
  "confidence": 0
}}

USER MESSAGE: {message}"""


def prompt_sybil(wallet_data: str) -> str:
    return f"""{get_date_prefix()}

Analyze these wallet behavior patterns to detect Sybil correlation.
Wallets with correlated behavior risk mass disqualification from airdrop protocols.

ANALYZE THESE 5 DIMENSIONS IN ORDER:

1. FUNDING SOURCE OVERLAP
   - Did the same address fund multiple wallets?
   - Were wallets funded within minutes of each other from the same source?
   - Are funding amounts suspiciously identical?

2. TRANSACTION TIMING CORRELATION
   - Do wallets execute transactions within 10 minutes of each other repeatedly?
   - Do they interact with the same protocol on the same day every time?
   - Is the time-between-transactions suspiciously uniform?

3. AMOUNT PATTERN SIMILARITY
   - Are transaction amounts identical or near-identical across wallets?
   - Do they always use the same round numbers?

4. GAS PRICE SIMILARITY
   - Do wallets consistently use identical gas prices?
   - Same gas multiplier every time = bot signal

5. PROTOCOL INTERACTION SEQUENCE
   - Do wallets hit the same protocols in the same order?
   - Same task sequence every cycle across multiple wallets?

For each suspicious wallet pair, output one entry.
Only include pairs with correlation_score >= 20.
Pairs below 20 can be omitted.

OUTPUT (JSON array only, no other text):
[
  {{
    "wallet_a": 0,
    "wallet_b": 0,
    "correlation_score": 0,
    "risk_level": "low | medium | high | critical",
    "evidence": [
      {{
        "dimension": "string",
        "finding": "string",
        "severity": "low | medium | high"
      }}
    ],
    "recommendation": "string"
  }}
]

WALLET ACTIVITY DATA:
{wallet_data}"""


def prompt_roi(project_data: str) -> str:
    return f"""{get_date_prefix()}

Estimate the potential airdrop value for this project.
Be conservative and transparent about uncertainty.
Never invent numbers — ground every estimate in comparable historical airdrops.

ANCHOR YOUR ESTIMATES to these verified historical airdrops:
- Large L2 (Arbitrum Mar 2023): $300 - $3,000 average per wallet
- Large L2 (Optimism May 2022): $200 - $1,500 average per wallet
- DeFi protocol (Uniswap Sep 2020): $400 - $2,000 average per wallet
- Bridge (LayerZero Jun 2024): $100 - $1,500 average per wallet
- Infrastructure (ENS Nov 2021): $500 - $10,000 (high variance)
- Small/new protocol: $20 - $300 average

FACTORS THAT INCREASE ALLOCATION:
- Early testnet user (multiplier effect)
- High transaction volume over extended period
- Long wallet age (6+ months of history)
- Governance participation (voting, proposals)
- Liquidity provision
- Diverse protocol usage across the ecosystem

FACTORS THAT DECREASE ALLOCATION:
- Recent activity only (last 30 days)
- Low transaction volume
- Few unique interactions
- Sybil flags or correlated behavior
- Single-protocol focus

OUTPUT (JSON only, no other text):
{{
  "project": "string",
  "estimated_usd": {{
    "conservative": 0,
    "realistic": 0,
    "optimistic": 0
  }},
  "confidence": 0,
  "comparable_used": [
    {{"project": "string", "avg_allocation_usd": 0, "similarity_reason": "string"}}
  ],
  "key_assumptions": ["string"],
  "factors_considered": ["string"],
  "data_quality_warning": "string | null"
}}

Note: Always include data_quality_warning if confidence < 50.

PROJECT DATA:
{project_data}"""


def prompt_gap(task_config_json: str, criteria_json: str) -> str:
    return f"""{get_date_prefix()}

Compare this project's eligibility criteria against the tasks currently configured.
Your analysis directly determines whether wallets will qualify for the airdrop.

IDENTIFY EACH OF THE FOLLOWING:

1. MISSING — criteria explicitly required by the project but no task configured to fulfill it
   Priority: "required" (must have) or "bonus" (adds eligibility weight)

2. UNSUPPORTED — tasks configured in the system but the project does not support or count this task type
   Example: governance task configured but protocol has no governance

3. OPTIONAL_BONUS — tasks not configured but would add meaningful eligibility weight if added
   Only include if there is evidence the protocol rewards this behavior

4. THRESHOLD_CHANGED — a threshold in the config differs from what the current criteria says
   Example: config says 5 swaps, criteria says 10 swaps

5. OUTDATED — criteria in config that have not been re-verified in more than 30 days
   Flag the field name and when it was last verified

OUTPUT (JSON only, no other text):
{{
  "protocol": "string",
  "missing_tasks": [
    {{
      "criteria_description": "string",
      "suggested_task_type": "string",
      "priority": "required | bonus",
      "reasoning": "string"
    }}
  ],
  "unsupported_tasks": [
    {{
      "task_type": "string",
      "reason": "string"
    }}
  ],
  "optional_bonus_tasks": [
    {{
      "task_type": "string",
      "expected_benefit": "string"
    }}
  ],
  "threshold_changes": [
    {{
      "task_type": "string",
      "configured_value": "string",
      "actual_value": "string",
      "impact": "string"
    }}
  ],
  "outdated_criteria": [
    {{
      "field": "string",
      "last_verified": "string",
      "days_since_check": 0
    }}
  ],
  "overall_confidence": 0,
  "summary": "string"
}}

CURRENT TASK CONFIG:
{task_config_json}

PROJECT CRITERIA:
{criteria_json}"""


def prompt_config_validation(config_json: str, context_json: str = "{}") -> str:
    return f"""{get_date_prefix()}

Review this proposed configuration change before it is applied to the airdrop farming system.
This config will drive real automated transactions. Errors cost gas and miss airdrops.

CHECK EACH OF THESE 11 POINTS IN ORDER:

1. AMOUNT RANGE — is min_amount too low (dust transactions look suspicious) or max_amount too high (risks significant loss)?
2. BIDIRECTIONAL TOKEN PAIR — if bidirectional=true, do both token_in→token_out AND token_in_reverse→token_out_reverse make logical sense?
3. ACTIVE HOURS — does the UTC active window make sense for the chain's typical user activity pattern?
4. SLEEP TIMING — is sleep_min_mins too short? Less than 1 minute between tasks looks like a bot.
5. GAS MULTIPLIER — is the multiplier safe for this chain? Very high multipliers waste gas, very low cause tx failures.
6. AMOUNT DISTRIBUTION — does weighted_low/weighted_high/uniform fit this task type? LP tasks suit weighted_high, small swaps suit weighted_low.
7. DAILY TX RANGE — is the min/max realistic for human behavior? More than 15 txs/day on one protocol is suspicious.
8. DAILY VARIANCE — is amount_vary_daily=true? If false, explain why fixed amounts are acceptable here.
9. TOKEN PAIR CORRECTNESS — are token_in and token_out valid symbols registered for this chain?
10. FREQUENCY — is frequency_mins reasonable? Too frequent (under 30 mins) on one protocol looks like automation.
11. START OFFSET — is start_offset_max_mins large enough to prevent simultaneous wallet starts? Should be at least 15 minutes.

For each issue found, set severity:
- "blocking" — will cause errors, failed txns, or obvious bot detection
- "warning" — suboptimal but will work
- "suggestion" — improvement but not critical

If approved is false, at least one issue must have severity "blocking".

OUTPUT (JSON only, no other text):
{{
  "config_type": "wallet_settings | task_config | project_config",
  "approved": false,
  "issues": [
    {{
      "check_number": 0,
      "field": "string",
      "problem": "string",
      "severity": "blocking | warning | suggestion",
      "recommended_value": "string | null"
    }}
  ],
  "improvements": ["string"],
  "confidence": 0,
  "summary": "string"
}}

PROPOSED CONFIG:
{config_json}

CONTEXT (chain, project, wallet info):
{context_json}"""

