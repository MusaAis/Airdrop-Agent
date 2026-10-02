"""
Telegram help text — one page per category.

This reflects the curated command set (PLAN.md §4): Telegram carries the
quick-action, mobile-friendly commands. Config-heavy, rarely-used, or
dashboard-duplicate commands live on the website instead — not listed here.
"""

HELP_PAGES = {
    "wallet": (
        "🔐 WALLET COMMANDS\n"
        "/wallet_create [count] [tag] — Generate HD wallets\n"
        "/wallet_list — All wallets\n"
        "/wallet_status [id] — Wallet details\n"
        "/wallet_balance [id/all] — Balances\n"
        "/wallet_pause [id/all] — Pause ⚠️\n"
        "/wallet_resume [id/all] — Resume\n"
        "/wallet_blacklist [id] — Blacklist ⚠️\n"
        "/wallet_archive [id] — Archive ⚠️\n"
        "/wallet_tag [id] [tag] — Add tag\n"
        "/wallet_group [tag] — List by tag\n"
        "/wallet_fund [id] [chain_id] — Gas refill\n"
        "/wallet_health [id] — Health score\n"
        "/wallet_sybil [id] — Sybil risk\n"
        "/wallet_top [n] — Top N wallets\n"
        "/wallet_failing — Failing wallets\n"
        "/wallet_set_gas [id] [true/false] — Toggle gas wallet\n\n"
        "More wallet settings (unblacklist, unarchive, untag, cooldown,\n"
        "persona, nonce status) are on the website dashboard."
    ),
    "chain": (
        "⛓️ CHAIN COMMANDS\n"
        "/chain_list — All chains\n"
        "/chain_add [name] [chain_id] [rpc] — Add chain\n"
        "/chain_enable [id] — Enable\n"
        "/chain_disable [id] — Disable ⚠️\n"
        "/chain_status [id] — RPC + gas status\n"
        "/chain_gas [id] — Current gas price\n"
        "/chain_add_token [chain_id] [sym] [addr] [dec] — Register token\n"
        "/chain_tokens [id] — Registered tokens\n\n"
        "RPC fallback management, rate limits, and gas token config are on\n"
        "the website dashboard."
    ),
    "task": (
        "📋 TASK COMMANDS\n"
        "/task_list [project_id] — List task configs\n"
        "/task_status [id] — Task details\n"
        "/task_enable [id] — Enable task\n"
        "/task_pause [id] — Pause task ⚠️\n"
        "/task_trigger [task_id] [wallet_id/random] — Run now\n\n"
        "Dependencies, priority, templates, and dry-run are on the website\n"
        "dashboard (dry-run is also a global toggle via /agent_dryrun)."
    ),
    "project": (
        "📁 PROJECT COMMANDS\n"
        "/project_add — Add a project (guided)\n"
        "/project_list — All projects\n"
        "/project_status [id] — Eligibility across wallets\n"
        "/project_enable [id] — Enable\n"
        "/project_disable [id] — Disable ⚠️\n"
        "/project_pause [id] — Pause ⚠️\n"
        "/project_resume [id] — Resume\n"
        "/project_approve [id] — Run AI risk/config review, then activate\n"
        "/project_reject [id] — Reject\n"
        "/project_gap [id] — AI audit: task config vs criteria\n"
        "/project_reset_circuit [id] — Reset auto-paused circuit breaker ⚠️\n\n"
        "Priority, wallet caps, criteria editing, and blacklist are on the\n"
        "website dashboard."
    ),
    "agent": (
        "🤖 AGENT COMMANDS\n"
        "/agent_status — Agent status\n"
        "/agent_start — Start agent\n"
        "/agent_stop — Graceful stop ⚠️\n"
        "/agent_pause_all — Pause all scheduling ⚠️\n"
        "/agent_resume_all — Resume all\n"
        "/agent_unlock [password] — Unlock seed\n\n"
        "Live worker/queue views are on the website dashboard."
    ),
    "report": (
        "📊 REPORT COMMANDS\n"
        "/report_eligibility [project_id] — Eligibility %\n"
        "/report_daily_progress [project_id] — Today tx vs target\n"
        "/report_gas [chain_id] — Gas usage + costs\n"
        "/report_server — Live RAM/CPU/workers\n\n"
        "Sybil report and full activity log are on the website dashboard."
    ),
    "faucet": (
        "🚰 FAUCET COMMANDS\n"
        "/faucet_request [wallet_id] [chain_id] — Manual trigger\n"
        "/faucet_bulk [chain_id] — Trigger for all wallets\n\n"
        "Faucet list and configuration are on the website dashboard."
    ),
    "claim": (
        "💰 CLAIM COMMANDS\n"
        "/claim_check — Scan for claimable airdrops\n"
        "/claim_eligible — List eligible wallets\n"
        "/claim_trigger [wallet_id] [project_id] — Execute ⚠️ (always manual)\n"
        "/claim_pending — Pending claims\n\n"
        "Claiming is always a manual, deliberate action — there is no\n"
        "auto-claim. Claim history is on the website dashboard."
    ),
    "config": (
        "🔄 CONFIG COMMANDS\n"
        "/config_show [wallet_id/all] — Show settings\n"
        "/config_set [wallet_id] [key] [value] — Change setting\n\n"
        "Keys: amounts, distribution, timing, active_hours,\n"
        "start_offset, bidirectional, gas_multiplier, daily_vary, daily_tx\n\n"
        "Reset-to-defaults is on the website dashboard (safer with a\n"
        "confirm dialog for a destructive action)."
    ),
    "ai": (
        "🧠 AI COMMANDS\n"
        "/ai_status — Groq + Gemini API status\n"
        "/ai_pending — Awaiting human decision\n"
        "/ai_approve [validation_id] — Approve validation\n"
        "/ai_reject [validation_id] — Reject validation\n"
        "/ai_autonomy_off — Freeze AI autonomous wallet/task management ⚠️\n"
        "/ai_autonomy_on — Resume AI autonomous management\n\n"
        "Full validation log and agreement scores are on the website\n"
        "AI Log page."
    ),
    "nonce": (
        "🔢 NONCE COMMANDS\n"
        "/nonce_release_all — Release all stuck nonce locks ⚠️\n\n"
        "Per-wallet nonce check/sync/release are on the website dashboard."
    ),
    "tx": (
        "📤 TX COMMANDS\n"
        "/tx_stuck — List stuck/pending transactions\n"
        "/tx_speedup [tx_id] — Speed up stuck tx ⚠️\n"
        "/tx_cancel [tx_id] — Cancel stuck tx ⚠️\n\n"
        "Full transaction history and hash verification are on the\n"
        "website Logs page."
    ),
    "gas": (
        "⛽ GAS COMMANDS\n"
        "/gas_price [chain_id] — Current gas price\n"
        "/gas_refill [wallet_id] [chain_id] — Manual refill ⚠️\n\n"
        "Spike status, optimal windows, cost history, and budgets are on\n"
        "the website dashboard."
    ),
    "alert": (
        "🔔 ALERT COMMANDS\n"
        "/alert_list — Active alerts\n"
        "/alert_resolve_all — Mark all resolved\n\n"
        "Snooze, single-resolve, test alert, and RAM threshold are on the\n"
        "website dashboard."
    ),
    "system": (
        "⚙️ SYSTEM COMMANDS\n"
        "/system_status — Full system health\n"
        "/system_version — Version + uptime\n"
        "/group_setup — (run inside the group) create report topics\n"
        "/group_status — Where reports are being sent\n"
        "/report_now [daily|weekly|monthly|ai] — Send a report now\n\n"
        "RPC testing, maintenance windows, and log archival are on the\n"
        "website dashboard. There is no automated backup system — back up\n"
        "the database yourself outside the app."
    ),
}

QUICK_HELP = (
    "🤖 Airdrop Agent — Command Categories\n\n"
    "Type /help [category] for details:\n\n"
    "  /help wallet    — Wallet management\n"
    "  /help chain     — Chain config\n"
    "  /help task      — Task management\n"
    "  /help project   — Project management\n"
    "  /help agent     — Agent control\n"
    "  /help report    — Reports & analytics\n"
    "  /help faucet    — Faucet management\n"
    "  /help claim     — Airdrop claims (manual only)\n"
    "  /help config    — Settings & config\n"
    "  /help ai        — AI validation & autonomy\n"
    "  /help nonce     — Nonce management\n"
    "  /help tx        — Transactions\n"
    "  /help gas       — Gas management\n"
    "  /help alert     — Alerts\n"
    "  /help system    — System status\n\n"
    "💬 Natural language works too!\n"
    "   Example: \"pause all wallets\"\n\n"
    "Most configuration-heavy actions live on the website dashboard —\n"
    "Telegram is the quick-action remote.\n\n"
    "/commands — Send all categories at once"
)


def get_full_command_list() -> str:
    return "\n\n".join(HELP_PAGES.values())

def get_quick_help() -> str:
    return QUICK_HELP

def get_category_help(category: str) -> str:
    cat = (category or "").lower().strip()
    if cat in HELP_PAGES:
        return HELP_PAGES[cat]
    return f"Unknown category '{cat}'\n\nAvailable: {', '.join(HELP_PAGES.keys())}\n\n{QUICK_HELP}"

def get_all_pages() -> list:
    return list(HELP_PAGES.values())
