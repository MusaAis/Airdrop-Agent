HELP_PAGES = {
    "wallet": (
        "🔐 WALLET COMMANDS\n"
        "/wallet_create [count] [tag] — Generate HD wallets\n"
        "/wallet_list — All wallets\n"
        "/wallet_status [id] — Wallet details\n"
        "/wallet_balance [id/all] — Balances\n"
        "/wallet_pause [id/all] — Pause ⚠️\n"
        "/wallet_resume [id/all] — Resume\n"
        "/wallet_cooldown [id] [hours] — Force cooldown ⚠️\n"
        "/wallet_blacklist [id] — Blacklist ⚠️\n"
        "/wallet_unblacklist [id] — Restore\n"
        "/wallet_archive [id] — Archive ⚠️\n"
        "/wallet_unarchive [id] — Restore archived\n"
        "/wallet_tag [id] [tag] — Add tag\n"
        "/wallet_untag [id] [tag] — Remove tag\n"
        "/wallet_group [tag] — List by tag\n"
        "/wallet_fund [id] [chain_id] — Gas refill\n"
        "/wallet_health [id] — Health score\n"
        "/wallet_sybil [id] — Sybil risk\n"
        "/wallet_persona [id] — Persona config\n"
        "/wallet_top [n] — Top N wallets\n"
        "/wallet_failing — Failing wallets\n"
        "/wallet_gas_wallets — Gas wallets\n"
        "/wallet_set_gas [id] [true/false] — Toggle gas wallet\n"
        "/wallet_nonce [id] [chain_id] — Nonce status"
    ),
    "chain": (
        "⛓️ CHAIN COMMANDS\n"
        "/chain_list — All chains\n"
        "/chain_add [name] [chain_id] [rpc] — Add chain\n"
        "/chain_enable [id] — Enable\n"
        "/chain_disable [id] — Disable ⚠️\n"
        "/chain_status [id] — RPC + gas status\n"
        "/chain_gas [id] — Current gas price\n"
        "/chain_rpc [id] [rpc] — Update primary RPC\n"
        "/chain_add_fallback [id] [rpc] — Add fallback RPC\n"
        "/chain_remove_fallback [id] [rpc] — Remove fallback\n"
        "/chain_test_rpc [id] — Test all RPCs\n"
        "/chain_tokens [id] — Registered tokens\n"
        "/chain_add_token [chain_id] [sym] [addr] [dec] — Register token\n"
        "/chain_gas_token [id] — Gas token config\n"
        "/chain_set_rate_limit [id] [req/sec] — RPC rate limit"
    ),
    "task": (
        "📋 TASK COMMANDS\n"
        "/task_list [project_id] — List task configs\n"
        "/task_status [id] — Task details\n"
        "/task_enable [id] — Enable task\n"
        "/task_pause [id] — Pause task ⚠️\n"
        "/task_trigger [task_id] [wallet_id/random] — Run now\n"
        "/task_dry_run [task_id] [wallet_id] — Simulate"
    ),
    "project": (
        "📁 PROJECT COMMANDS\n"
        "/project_list — All projects\n"
        "/project_add [name] — Add project\n"
        "/project_status [id] — Eligibility across wallets\n"
        "/project_enable [id] — Enable\n"
        "/project_disable [id] — Disable ⚠️\n"
        "/project_pause [id] — Pause ⚠️\n"
        "/project_resume [id] — Resume"
    ),
    "agent": (
        "🤖 AGENT COMMANDS\n"
        "/agent_status — Agent status\n"
        "/agent_start — Start agent\n"
        "/agent_stop — Graceful stop ⚠️\n"
        "/agent_workers — Worker slots view\n"
        "/agent_queue — Priority queue\n"
        "/agent_pause_all — Pause all scheduling ⚠️\n"
        "/agent_resume_all — Resume all\n"
        "/agent_unlock [password] — Unlock seed"
    ),
    "report": (
        "📊 REPORT COMMANDS\n"
        "/report_eligibility [project_id] — Eligibility %\n"
        "/report_roi [project_id] — Gas vs estimated value\n"
        "/report_daily_progress [project_id] — Today tx vs target\n"
        "/report_gas [chain_id] — Gas usage + costs\n"
        "/report_sybil — Sybil risk scores\n"
        "/report_activity [hours] — Recent transactions\n"
        "/report_server — Live RAM/CPU/workers"
    ),
    "faucet": (
        "🚰 FAUCET COMMANDS\n"
        "/faucet_list [chain_id] — List faucets\n"
        "/faucet_request [wallet_id] [chain_id] — Manual trigger\n"
        "/faucet_bulk [chain_id] — Trigger for all wallets"
    ),
    "claim": (
        "💰 CLAIM COMMANDS\n"
        "/claim_check — Scan for claimable airdrops\n"
        "/claim_eligible — List eligible wallets\n"
        "/claim_value [project_id] — Estimated USD value\n"
        "/claim_trigger [wallet_id] [project_id] — Execute ⚠️\n"
        "/claim_set_threshold [usd] — Auto-claim threshold\n"
        "/claim_auto_on — Enable auto-claim\n"
        "/claim_auto_off — Disable auto-claim\n"
        "/claim_pending — Pending high-value claims\n"
        "/claim_history — Recent history"
    ),
    "config": (
        "🔄 CONFIG COMMANDS\n"
        "/config_show [wallet_id/all] — Show settings\n"
        "/config_set [wallet_id] [key] [value] — Change setting\n"
        "/config_reset [wallet_id/all] — Reset to defaults ⚠️\n\n"
        "Keys: amounts, distribution, timing, active_hours,\n"
        "start_offset, bidirectional, gas_multiplier,\n"
        "daily_vary, daily_tx, max_workers, task_timeout,\n"
        "gas_spike_multiplier, memory_limit, auto_claim_threshold"
    ),
    "ai": (
        "🧠 AI COMMANDS\n"
        "/ai_log [n] — Last N AI validations\n"
        "/ai_validate [project_id] — Re-validate project\n"
        "/ai_approve [validation_id] — Approve validation\n"
        "/ai_reject [validation_id] — Reject validation\n"
        "/ai_pending — Awaiting human decision\n"
        "/ai_status — Groq + Gemini API status\n"
        "/ai_agreement [n] — Agreement scores"
    ),
    "nonce": (
        "🔢 NONCE COMMANDS\n"
        "/nonce_check [wallet_id] [chain_id] — Nonce status\n"
        "/nonce_sync [wallet_id] [chain_id] — Resync from chain\n"
        "/nonce_release [wallet_id] [chain_id] — Release stuck ⚠️\n"
        "/nonce_release_all — Release all stuck nonces ⚠️"
    ),
    "tx": (
        "📤 TX COMMANDS\n"
        "/tx_stuck — List stuck/pending transactions\n"
        "/tx_speedup [tx_id] — Speed up stuck tx ⚠️\n"
        "/tx_cancel [tx_id] — Cancel stuck tx ⚠️\n"
        "/tx_status [tx_hash] — Check tx on-chain\n"
        "/tx_failed [hours] — Recent failed txs\n"
        "/tx_verify [wallet_id] — Re-verify tx hashes"
    ),
    "gas": (
        "⛽ GAS COMMANDS\n"
        "/gas_price [chain_id] — Current gas price\n"
        "/gas_spike [chain_id] — Spike status\n"
        "/gas_optimal — Best time windows to transact\n"
        "/gas_cost [wallet_id] [hours] — Total gas cost\n"
        "/gas_budget [wallet_id] [usd/day] — Set daily budget\n"
        "/gas_refill [wallet_id] [chain_id] — Manual refill ⚠️"
    ),
    "discovery": (
        "🔭 DISCOVERY COMMANDS\n"
        "/discovery_run — Trigger discovery scan\n"
        "/discovery_sources — List sources\n"
        "/discovery_enable [source] — Enable source\n"
        "/discovery_disable [source] — Disable source\n"
        "/discovery_pending — Projects awaiting approval\n"
        "/discovery_set_interval [hours] — Set frequency"
    ),
    "proxy": (
        "🛠️ PROXY COMMANDS\n"
        "/proxy_list — All proxies\n"
        "/proxy_add [url] [type] — Add proxy\n"
        "/proxy_assign [wallet_id] [url] — Assign to wallet\n"
        "/proxy_unassign [wallet_id] — Remove assignment\n"
        "/proxy_check [wallet_id] — Test connectivity\n"
        "/proxy_rotate [wallet_id] — Rotate to next proxy\n"
        "/proxy_status — All proxy health"
    ),
    "alert": (
        "🔔 ALERT COMMANDS\n"
        "/alert_snooze [minutes] — Silence non-critical alerts\n"
        "/alert_unsnooze — Re-enable all alerts\n"
        "/alert_test — Send test notification\n"
        "/alert_list — Active alerts\n"
        "/alert_resolve [id] — Mark resolved\n"
        "/alert_resolve_all — Mark all resolved\n"
        "/alert_memory [pct] — Custom RAM alert threshold"
    ),
    "system": (
        "⚙️ SYSTEM COMMANDS\n"
        "/system_status — Full system health\n"
        "/system_backup — Trigger encrypted backup ⚠️\n"
        "/system_test_rpc [chain_id] — Test RPC\n"
        "/system_maintenance [start] [end] — Set maintenance window\n"
        "/system_maintenance_off — Cancel maintenance window\n"
        "/system_log_archive — Archive old logs\n"
        "/system_version — Version + uptime"
    ),
    "schedule": (
        "📅 SCHEDULE COMMANDS\n"
        "/schedule_next [n] — Next N scheduled tasks\n"
        "/schedule_pause [wallet_id] — Pause wallet schedule ⚠️\n"
        "/schedule_resume [wallet_id] — Resume wallet schedule"
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
    "  /help claim     — Airdrop claims\n"
    "  /help config    — Settings & config\n"
    "  /help ai        — AI validation\n"
    "  /help nonce     — Nonce management\n"
    "  /help tx        — Transactions\n"
    "  /help gas       — Gas management\n"
    "  /help discovery — Project discovery\n"
    "  /help proxy     — Proxy management\n"
    "  /help alert     — Alerts\n"
    "  /help system    — System & backups\n"
    "  /help schedule  — Scheduling\n\n"
    "💬 Natural language works too!\n"
    "   Example: \"pause all wallets\"\n\n"
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
