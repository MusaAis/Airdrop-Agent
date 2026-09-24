import logging
import inspect
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from backend.config import TELEGRAM_BOT_TOKEN
from backend.telegram.whitelist import is_whitelisted
from backend.telegram.nl_parser import parse_natural_language
from backend.telegram.commands.wallet import (
    handle_wallet_create, handle_wallet_list, handle_wallet_status,
    handle_wallet_balance, handle_wallet_pause, handle_wallet_resume,
    handle_wallet_cooldown, handle_wallet_blacklist, handle_wallet_unblacklist,
    handle_wallet_archive, handle_wallet_unarchive, handle_wallet_tag,
    handle_wallet_untag, handle_wallet_group, handle_wallet_fund,
    handle_wallet_health, handle_wallet_sybil, handle_wallet_persona,
    handle_wallet_top, handle_wallet_failing, handle_wallet_gas_wallets,
    handle_wallet_set_gas, handle_wallet_nonce, handle_wallet_warmup,
)
from backend.telegram.commands.chain import (
    handle_chain_list, handle_chain_add, handle_chain_enable, handle_chain_disable,
    handle_chain_status, handle_chain_gas, handle_chain_tokens, handle_chain_rpc,
    handle_chain_add_fallback, handle_chain_remove_fallback, handle_chain_test_rpc,
    handle_chain_add_token, handle_chain_gas_token, handle_chain_set_rate_limit
)
from backend.telegram.commands.task import (
    handle_task_list, handle_task_status, handle_task_enable, handle_task_pause,
    handle_task_trigger, handle_task_dry_run,
    handle_task_deps, handle_task_set_priority, handle_task_trigger_all, handle_task_template,
)
from backend.telegram.commands.project import (
    handle_project_list, handle_project_add, handle_project_status,
    handle_project_disable, handle_project_enable, handle_project_pause, handle_project_resume,
    handle_project_approve, handle_project_reject, handle_project_farm,
    handle_project_prioritize, handle_project_cap, handle_project_update,
    handle_project_criteria, handle_project_gap, handle_project_blacklist,
    handle_project_circuit_breaker, handle_project_reset_circuit,
)
from backend.telegram.commands.faucet import (
    handle_faucet_list, handle_faucet_request, handle_faucet_bulk,
    handle_faucet_add, handle_faucet_add_fallback, handle_faucet_enable,
    handle_faucet_disable, handle_faucet_status, handle_faucet_history,
)
from backend.telegram.commands.report import (
    handle_report_eligibility, handle_report_roi, handle_report_daily_progress,
    handle_report_gas, handle_report_sybil, handle_report_activity, handle_report_server,
    handle_report_wallets, handle_report_weekly, handle_report_snapshot,
    handle_report_failed, handle_report_gas_estimate, handle_report_compare, handle_report_project,
)
from backend.telegram.commands.config import (
    handle_config_set, handle_config_show, handle_config_reset
)
from backend.telegram.commands.agent_extras import (
    handle_agent_start, handle_agent_stop, handle_agent_pause_all,
    handle_agent_resume_all, handle_agent_workers, handle_agent_queue
)
from backend.telegram.commands.schedule import (
    handle_schedule_next, handle_schedule_pause, handle_schedule_resume,
    handle_schedule_set, handle_schedule_set_window,
)
from backend.telegram.commands.claim import (
    handle_claim_check, handle_claim_eligible, handle_claim_value,
    handle_claim_trigger, handle_claim_set_threshold, handle_claim_auto_on,
    handle_claim_auto_off, handle_claim_pending, handle_claim_history
)
from backend.telegram.commands.ai import (
    handle_ai_log, handle_ai_validate, handle_ai_approve, handle_ai_reject,
    handle_ai_pending, handle_ai_status, handle_ai_agreement
)
from backend.telegram.commands.nonce import (
    handle_nonce_check, handle_nonce_sync, handle_nonce_release, handle_nonce_release_all
)
from backend.telegram.commands.tx import (
    handle_tx_stuck, handle_tx_speedup, handle_tx_cancel, handle_tx_status,
    handle_tx_failed, handle_tx_verify
)
from backend.telegram.commands.gas import (
    handle_gas_price, handle_gas_spike, handle_gas_optimal,
    handle_gas_cost, handle_gas_budget, handle_gas_refill, handle_gas_history,
)
from backend.telegram.commands.discovery import (
    handle_discovery_run, handle_discovery_sources, handle_discovery_enable,
    handle_discovery_disable, handle_discovery_pending, handle_discovery_set_interval
)
from backend.telegram.commands.proxy import (
    handle_proxy_list, handle_proxy_add, handle_proxy_assign,
    handle_proxy_unassign, handle_proxy_check, handle_proxy_rotate, handle_proxy_status
)
from backend.telegram.commands.alert import (
    handle_alert_snooze, handle_alert_unsnooze, handle_alert_test,
    handle_alert_list, handle_alert_resolve, handle_alert_resolve_all, handle_alert_memory
)
from backend.telegram.commands.system import (
    handle_system_status, handle_system_backup, handle_system_test_rpc,
    handle_system_maintenance, handle_system_maintenance_off, handle_system_log_archive,
    handle_system_version
)
from backend.telegram.commands.agent import (
    handle_agent_status, handle_agent_stop as handle_agent_stop_simple, handle_agent_unlock,
    handle_agent_kill, handle_agent_dryrun_on, handle_agent_dryrun_off,
    handle_agent_restart, handle_agent_schedule_preview,
)
from backend.telegram.sender import set_bot_app


# -------------------------------------------------------------------
# Pending-confirmation state machine for ⚠️ destructive commands
# {user_id: {"action": str, "params": dict, "expires_at": float}}
# -------------------------------------------------------------------
import time as _time
_PENDING_CONFIRMATIONS: dict = {}
_CONFIRM_TTL_SECS: int = 60  # confirmation expires after 60 s

def _set_pending(user_id: int, action: str, params: dict):
    _PENDING_CONFIRMATIONS[user_id] = {
        "action": action,
        "params": params,
        "expires_at": _time.monotonic() + _CONFIRM_TTL_SECS,
    }

def _pop_pending(user_id: int):
    entry = _PENDING_CONFIRMATIONS.pop(user_id, None)
    if entry and _time.monotonic() > entry["expires_at"]:
        return None  # expired
    return entry

def _cancel_pending(user_id: int):
    _PENDING_CONFIRMATIONS.pop(user_id, None)

# Actions that require a "confirm" reply before executing
_CONFIRM_REQUIRED = {
    "agent.kill", "wallet.blacklist", "chain.disable",
    "config.reset", "nonce.release_all", "system.backup",
}

logger = logging.getLogger("airdrop.telegram.bot")
app = None


def get_bot_app():
    return app


# -------------------------------------------------------------------
# Smart make_cmd: auto-detects handler signature and calls correctly
# Handles 3 patterns:
#   (user_id, db)                        — agent.py handlers
#   (user_id, db, confirmation=None)     — agent_extras.py handlers
#   (user_id, args, db, confirmation=None) — all other handlers
# -------------------------------------------------------------------
def make_cmd(handler):
    sig = inspect.signature(handler)
    param_names = list(sig.parameters.keys())

    async def _cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_whitelisted(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized")
            return
        from backend.database import async_session
        async with async_session() as db:
            try:
                if "args" in param_names:
                    # Pattern: (user_id, args, db, ...)
                    response = await handler(update.effective_user.id, context.args or [], db)
                elif len(param_names) == 2:
                    # Pattern: (user_id, db)
                    response = await handler(update.effective_user.id, db)
                else:
                    # Pattern: (user_id, db, confirmation=None)
                    response = await handler(update.effective_user.id, db)
            except Exception as e:
                logger.exception("Handler error: %s", e)
                response = f"❌ Error: {str(e)}"
        await update.message.reply_text(response or "✅ Done.")

    return _cmd


# -------------------------------------------------------------------
# Shared action dispatcher
# -------------------------------------------------------------------
async def dispatch_action(user_id: int, action: str, params: dict, db) -> str:
    resp = f"⚠️ Unknown action: '{action}'. Try /help"
    try:
        # Stage destructive actions and wait for "confirm" reply
        if action in _CONFIRM_REQUIRED:
            _set_pending(user_id, action, params)
            labels = {
                "agent.kill": "🔴 EMERGENCY STOP — halt all agent activity",
                "wallet.blacklist": "⛔ Blacklist wallet",
                "chain.disable": "⚠️ Disable chain",
                "config.reset": "⚠️ Reset configuration to defaults",
                "nonce.release_all": "⚠️ Release all nonce locks",
                "system.backup": "💾 Trigger manual backup",
            }
            label = labels.get(action, f"Execute {action}")
            return f"⚠️ {label}\n\nReply *confirm* to proceed or *cancel* to abort. (expires in 60 s)"

        # WALLET
        if action == "wallet.create":
            count = params.get("count", 1); tag = params.get("tag")
            args = [str(count)] + ([tag] if tag else [])
            resp = await handle_wallet_create(user_id, args, db)
        elif action == "wallet.list":
            resp = await handle_wallet_list(user_id, [], db)
        elif action == "wallet.status":
            wid = params.get("id") or params.get("address")
            resp = await handle_wallet_status(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.balance":
            resp = await handle_wallet_balance(user_id, [str(params.get("id","all"))], db)
        elif action == "wallet.pause":
            resp = await handle_wallet_pause(user_id, [str(params.get("id","all"))], db)
        elif action == "wallet.resume":
            resp = await handle_wallet_resume(user_id, [str(params.get("id","all"))], db)
        elif action == "wallet.cooldown":
            wid = params.get("id"); hours = params.get("hours", 24)
            resp = await handle_wallet_cooldown(user_id, [str(wid), str(hours)], db) if wid else "Missing id"
        elif action == "wallet.blacklist":
            wid = params.get("id")
            resp = await handle_wallet_blacklist(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.unblacklist":
            wid = params.get("id")
            resp = await handle_wallet_unblacklist(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.archive":
            wid = params.get("id")
            resp = await handle_wallet_archive(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.unarchive":
            wid = params.get("id")
            resp = await handle_wallet_unarchive(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.tag":
            wid = params.get("id"); tag = params.get("tag")
            resp = await handle_wallet_tag(user_id, [str(wid), tag], db) if wid and tag else "Missing id/tag"
        elif action == "wallet.untag":
            wid = params.get("id"); tag = params.get("tag")
            resp = await handle_wallet_untag(user_id, [str(wid), tag], db) if wid and tag else "Missing id/tag"
        elif action == "wallet.group":
            tag = params.get("tag")
            resp = await handle_wallet_group(user_id, [tag], db) if tag else "Missing tag"
        elif action == "wallet.fund":
            wid = params.get("id"); cid = params.get("chain_id")
            resp = await handle_wallet_fund(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing id/chain_id"
        elif action == "wallet.health":
            wid = params.get("id")
            resp = await handle_wallet_health(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.sybil":
            wid = params.get("id")
            resp = await handle_wallet_sybil(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.persona":
            wid = params.get("id")
            resp = await handle_wallet_persona(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.top":
            resp = await handle_wallet_top(user_id, [str(params.get("n", 10))], db)
        elif action == "wallet.failing":
            resp = await handle_wallet_failing(user_id, [], db)
        elif action == "wallet.gas_wallets":
            resp = await handle_wallet_gas_wallets(user_id, [], db)
        elif action == "wallet.set_gas":
            wid = params.get("id"); val = params.get("value", "true")
            resp = await handle_wallet_set_gas(user_id, [str(wid), str(val)], db) if wid else "Missing id"
        elif action == "wallet.nonce":
            wid = params.get("id"); cid = params.get("chain_id")
            resp = await handle_wallet_nonce(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing id/chain_id"

        # CHAIN
        elif action == "chain.list":
            resp = await handle_chain_list(user_id, [], db)
        elif action == "chain.add":
            name = params.get("name"); cid = params.get("chain_id"); rpc = params.get("rpc")
            resp = await handle_chain_add(user_id, [name, str(cid), rpc], db) if all([name, cid, rpc]) else "Missing name/chain_id/rpc"
        elif action == "chain.enable":
            resp = await handle_chain_enable(user_id, [str(params.get("id",""))], db)
        elif action == "chain.disable":
            resp = await handle_chain_disable(user_id, [str(params.get("id",""))], db)
        elif action == "chain.status":
            resp = await handle_chain_status(user_id, [str(params.get("id",""))], db)
        elif action == "chain.gas":
            resp = await handle_chain_gas(user_id, [str(params.get("id",""))], db)
        elif action == "chain.tokens":
            resp = await handle_chain_tokens(user_id, [str(params.get("id",""))], db)
        elif action == "chain.rpc":
            cid = params.get("id"); rpc = params.get("rpc")
            resp = await handle_chain_rpc(user_id, [str(cid), rpc], db) if cid and rpc else "Missing id/rpc"
        elif action == "chain.add_fallback":
            cid = params.get("id"); rpc = params.get("rpc")
            resp = await handle_chain_add_fallback(user_id, [str(cid), rpc], db) if cid and rpc else "Missing id/rpc"
        elif action == "chain.remove_fallback":
            cid = params.get("id"); rpc = params.get("rpc")
            resp = await handle_chain_remove_fallback(user_id, [str(cid), rpc], db) if cid and rpc else "Missing id/rpc"
        elif action == "chain.test_rpc":
            resp = await handle_chain_test_rpc(user_id, [str(params.get("id",""))], db)
        elif action == "chain.add_token":
            cid = params.get("chain_id"); sym = params.get("symbol"); addr = params.get("address"); dec = params.get("decimals")
            resp = await handle_chain_add_token(user_id, [str(cid), sym, addr, str(dec)], db) if all([cid,sym,addr,dec]) else "Missing args"
        elif action == "chain.gas_token":
            resp = await handle_chain_gas_token(user_id, [str(params.get("id",""))], db)
        elif action == "chain.set_rate_limit":
            cid = params.get("id"); rate = params.get("req_sec")
            resp = await handle_chain_set_rate_limit(user_id, [str(cid), str(rate)], db) if cid and rate else "Missing id/req_sec"

        # TASK
        elif action == "task.list":
            pid = params.get("project_id")
            resp = await handle_task_list(user_id, [str(pid)] if pid else [], db)
        elif action == "task.status":
            resp = await handle_task_status(user_id, [str(params.get("id",""))], db)
        elif action == "task.enable":
            resp = await handle_task_enable(user_id, [str(params.get("id",""))], db)
        elif action == "task.pause":
            resp = await handle_task_pause(user_id, [str(params.get("id",""))], db)
        elif action == "task.trigger":
            tid = params.get("task_id"); wid = params.get("wallet_id", "random")
            resp = await handle_task_trigger(user_id, [str(tid), str(wid)], db) if tid else "Missing task_id"
        elif action == "task.dry_run":
            tid = params.get("task_id"); wid = params.get("wallet_id")
            resp = await handle_task_dry_run(user_id, [str(tid), str(wid)], db) if tid and wid else "Missing task_id/wallet_id"

        # PROJECT
        elif action == "project.list":
            resp = await handle_project_list(user_id, [], db)
        elif action == "project.add":
            name = params.get("name")
            resp = await handle_project_add(user_id, [name], db) if name else "Missing name"
        elif action == "project.status":
            resp = await handle_project_status(user_id, [str(params.get("id",""))], db)
        elif action == "project.disable":
            resp = await handle_project_disable(user_id, [str(params.get("id",""))], db)
        elif action == "project.enable":
            resp = await handle_project_enable(user_id, [str(params.get("id",""))], db)
        elif action == "project.pause":
            resp = await handle_project_pause(user_id, [str(params.get("id",""))], db)
        elif action == "project.resume":
            resp = await handle_project_resume(user_id, [str(params.get("id",""))], db)

        # PROJECT (additional)
        elif action == "project.approve":
            resp = await handle_project_approve(user_id, [str(params.get("id",""))], db)
        elif action == "project.reject":
            resp = await handle_project_reject(user_id, [str(params.get("id",""))], db)
        elif action == "project.farm":
            resp = await handle_project_farm(user_id, [str(params.get("id",""))], db)
        elif action == "project.prioritize":
            resp = await handle_project_prioritize(user_id, [str(params.get("id","")), str(params.get("priority","5"))], db)
        elif action == "project.cap":
            resp = await handle_project_cap(user_id, [str(params.get("id","")), str(params.get("max_wallets","2"))], db)
        elif action == "project.update":
            resp = await handle_project_update(user_id, [str(params.get("id",""))], db)
        elif action == "project.criteria":
            resp = await handle_project_criteria(user_id, [str(params.get("id",""))], db)
        elif action == "project.gap":
            resp = await handle_project_gap(user_id, [str(params.get("id",""))], db)
        elif action == "project.blacklist":
            resp = await handle_project_blacklist(user_id, [params.get("name","")], db)
        elif action == "project.circuit_breaker":
            resp = await handle_project_circuit_breaker(user_id, [str(params.get("id",""))], db)
        elif action == "project.reset_circuit":
            resp = await handle_project_reset_circuit(user_id, [str(params.get("id",""))], db)

        # FAUCET (additional)
        elif action == "faucet.add":
            resp = await handle_faucet_add(user_id, [str(params.get("chain_id","")), str(params.get("url","")), str(params.get("cooldown_hours",24))], db)
        elif action == "faucet.add_fallback":
            resp = await handle_faucet_add_fallback(user_id, [str(params.get("faucet_id","")), str(params.get("url",""))], db)
        elif action == "faucet.enable":
            resp = await handle_faucet_enable(user_id, [str(params.get("id",""))], db)
        elif action == "faucet.disable":
            resp = await handle_faucet_disable(user_id, [str(params.get("id",""))], db)
        elif action == "faucet.status":
            resp = await handle_faucet_status(user_id, [str(params.get("wallet_id",""))], db)
        elif action == "faucet.history":
            wid = params.get("wallet_id"); resp = await handle_faucet_history(user_id, [str(wid)] if wid else [], db)

        # SCHEDULE (additional)
        elif action == "schedule.set":
            resp = await handle_schedule_set(user_id, [str(params.get("task_id","")), str(params.get("mins",""))], db)
        elif action == "schedule.set_window":
            resp = await handle_schedule_set_window(user_id, [str(params.get("wallet_id","")), str(params.get("start","")), str(params.get("end",""))], db)

        # REPORT (additional)
        elif action == "report.wallets":
            resp = await handle_report_wallets(user_id, [], db)
        elif action == "report.weekly":
            resp = await handle_report_weekly(user_id, [], db)
        elif action == "report.snapshot":
            resp = await handle_report_snapshot(user_id, [], db)
        elif action == "report.failed":
            resp = await handle_report_failed(user_id, [str(params.get("hours",24))], db)
        elif action == "report.gas_estimate":
            resp = await handle_report_gas_estimate(user_id, [str(params.get("project_id",""))], db)
        elif action == "report.compare":
            resp = await handle_report_compare(user_id, [str(params.get("wallet_id1","")), str(params.get("wallet_id2",""))], db)
        elif action == "report.project":
            resp = await handle_report_project(user_id, [str(params.get("id", params.get("project_id","")))], db)

        # TASK (additional)
        elif action == "task.deps":
            resp = await handle_task_deps(user_id, [str(params.get("id",""))], db)
        elif action == "task.set_priority":
            resp = await handle_task_set_priority(user_id, [str(params.get("id","")), str(params.get("priority",""))], db)
        elif action == "task.trigger_all":
            resp = await handle_task_trigger_all(user_id, [str(params.get("project_id",""))], db)
        elif action == "task.template":
            resp = await handle_task_template(user_id, [params.get("name","list")], db)

        # AGENT (additional)
        elif action == "agent.restart":
            resp = await handle_agent_restart(user_id, db)
        elif action == "agent.schedule_preview":
            resp = await handle_agent_schedule_preview(user_id, db)

        # GAS (additional)
        elif action == "gas.history":
            resp = await handle_gas_history(user_id, [str(params.get("chain_id",""))], db)

        # WALLET (additional)
        elif action == "wallet.warmup":
            resp = await handle_wallet_warmup(user_id, [str(params.get("id",""))], db)
        elif action == "agent.status":
            resp = await handle_agent_status(user_id, db)
        elif action == "agent.start":
            resp = await handle_agent_start(user_id, db)
        elif action == "agent.stop":
            resp = await handle_agent_stop_simple(user_id, db)
        elif action == "agent.pause_all":
            resp = await handle_agent_pause_all(user_id, db)
        elif action == "agent.resume_all":
            resp = await handle_agent_resume_all(user_id, db)
        elif action == "agent.workers":
            resp = await handle_agent_workers(user_id, db)
        elif action == "agent.queue":
            resp = await handle_agent_queue(user_id, db)
        elif action == "agent.kill":
            resp = await handle_agent_kill(user_id, db)
        elif action == "agent.dryrun":
            resp = await handle_agent_dryrun_on(user_id, db)
        elif action == "agent.dryrun_off":
            resp = await handle_agent_dryrun_off(user_id, db)

        # FAUCET
        elif action == "faucet.list":
            cid = params.get("chain_id")
            resp = await handle_faucet_list(user_id, [str(cid)] if cid else [], db)
        elif action == "faucet.request":
            wid = params.get("wallet_id"); cid = params.get("chain_id")
            resp = await handle_faucet_request(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing wallet_id/chain_id"
        elif action == "faucet.bulk":
            cid = params.get("chain_id")
            resp = await handle_faucet_bulk(user_id, [str(cid)] if cid else [], db)

        # SCHEDULE
        elif action == "schedule.next":
            resp = await handle_schedule_next(user_id, [str(params.get("n", 10))], db)
        elif action == "schedule.pause":
            wid = params.get("wallet_id")
            resp = await handle_schedule_pause(user_id, [str(wid)], db) if wid else "Missing wallet_id"
        elif action == "schedule.resume":
            wid = params.get("wallet_id")
            resp = await handle_schedule_resume(user_id, [str(wid)], db) if wid else "Missing wallet_id"

        # CLAIM
        elif action == "claim.check":
            resp = await handle_claim_check(user_id, [], db)
        elif action == "claim.eligible":
            resp = await handle_claim_eligible(user_id, [], db)
        elif action == "claim.value":
            pid = params.get("project_id")
            resp = await handle_claim_value(user_id, [str(pid)] if pid else [], db)
        elif action == "claim.trigger":
            wid = params.get("wallet_id"); pid = params.get("project_id")
            resp = await handle_claim_trigger(user_id, [str(wid), str(pid)], db) if wid and pid else "Missing wallet_id/project_id"
        elif action == "claim.set_threshold":
            usd = params.get("usd")
            resp = await handle_claim_set_threshold(user_id, [str(usd)], db) if usd else "Missing usd"
        elif action == "claim.auto_on":
            resp = await handle_claim_auto_on(user_id, [], db)
        elif action == "claim.auto_off":
            resp = await handle_claim_auto_off(user_id, [], db)
        elif action == "claim.pending":
            resp = await handle_claim_pending(user_id, [], db)
        elif action == "claim.history":
            resp = await handle_claim_history(user_id, [], db)

        # REPORT
        elif action == "report.eligibility":
            pid = params.get("project_id")
            resp = await handle_report_eligibility(user_id, [str(pid)] if pid else [], db)
        elif action == "report.roi":
            pid = params.get("project_id")
            resp = await handle_report_roi(user_id, [str(pid)] if pid else [], db)
        elif action == "report.daily_progress":
            pid = params.get("project_id")
            resp = await handle_report_daily_progress(user_id, [str(pid)] if pid else [], db)
        elif action == "report.gas":
            cid = params.get("chain_id")
            resp = await handle_report_gas(user_id, [str(cid)] if cid else [], db)
        elif action == "report.sybil":
            resp = await handle_report_sybil(user_id, [], db)
        elif action == "report.activity":
            resp = await handle_report_activity(user_id, [str(params.get("hours", 24))], db)
        elif action == "report.server":
            resp = await handle_report_server(user_id, [], db)

        # CONFIG
        elif action == "config.show":
            resp = await handle_config_show(user_id, [str(params.get("wallet_id","all"))], db)
        elif action == "config.set":
            key = params.get("key"); val = params.get("value"); wid = params.get("wallet_id","all")
            resp = await handle_config_set(user_id, [str(wid), str(key), str(val)], db) if key and val else "Missing key/value"
        elif action == "config.reset":
            resp = await handle_config_reset(user_id, [str(params.get("wallet_id","all"))], db)

        # AI
        elif action == "ai.log":
            resp = await handle_ai_log(user_id, [str(params.get("n", 10))], db)
        elif action == "ai.validate":
            pid = params.get("project_id")
            resp = await handle_ai_validate(user_id, [str(pid)], db) if pid else "Missing project_id"
        elif action == "ai.approve":
            vid = params.get("validation_id")
            resp = await handle_ai_approve(user_id, [str(vid)], db) if vid else "Missing validation_id"
        elif action == "ai.reject":
            vid = params.get("validation_id")
            resp = await handle_ai_reject(user_id, [str(vid)], db) if vid else "Missing validation_id"
        elif action == "ai.pending":
            resp = await handle_ai_pending(user_id, [], db)
        elif action == "ai.status":
            resp = await handle_ai_status(user_id, [], db)
        elif action == "ai.agreement":
            resp = await handle_ai_agreement(user_id, [str(params.get("n", 10))], db)

        # NONCE
        elif action == "nonce.check":
            wid = params.get("wallet_id"); cid = params.get("chain_id")
            resp = await handle_nonce_check(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing wallet_id/chain_id"
        elif action == "nonce.sync":
            wid = params.get("wallet_id"); cid = params.get("chain_id")
            resp = await handle_nonce_sync(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing wallet_id/chain_id"
        elif action == "nonce.release":
            wid = params.get("wallet_id"); cid = params.get("chain_id")
            resp = await handle_nonce_release(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing wallet_id/chain_id"
        elif action == "nonce.release_all":
            resp = await handle_nonce_release_all(user_id, [], db)

        # TX
        elif action == "tx.stuck":
            resp = await handle_tx_stuck(user_id, [], db)
        elif action == "tx.speedup":
            tid = params.get("tx_id")
            resp = await handle_tx_speedup(user_id, [str(tid)], db) if tid else "Missing tx_id"
        elif action == "tx.cancel":
            tid = params.get("tx_id")
            resp = await handle_tx_cancel(user_id, [str(tid)], db) if tid else "Missing tx_id"
        elif action == "tx.status":
            h = params.get("tx_hash")
            resp = await handle_tx_status(user_id, [h], db) if h else "Missing tx_hash"
        elif action == "tx.failed":
            resp = await handle_tx_failed(user_id, [str(params.get("hours", 24))], db)
        elif action == "tx.verify":
            wid = params.get("wallet_id")
            resp = await handle_tx_verify(user_id, [str(wid)], db) if wid else "Missing wallet_id"

        # GAS
        elif action == "gas.price":
            cid = params.get("chain_id")
            resp = await handle_gas_price(user_id, [str(cid)], db) if cid else "Missing chain_id"
        elif action == "gas.spike":
            cid = params.get("chain_id")
            resp = await handle_gas_spike(user_id, [str(cid)], db) if cid else "Missing chain_id"
        elif action == "gas.optimal":
            resp = await handle_gas_optimal(user_id, [str(params.get("chain_id",""))], db)
        elif action == "gas.cost":
            wid = params.get("wallet_id")
            resp = await handle_gas_cost(user_id, [str(wid), str(params.get("hours",24))], db) if wid else "Missing wallet_id"
        elif action == "gas.budget":
            wid = params.get("wallet_id"); usd = params.get("usd_per_day")
            resp = await handle_gas_budget(user_id, [str(wid), str(usd)], db) if wid and usd else "Missing wallet_id/usd_per_day"
        elif action == "gas.refill":
            wid = params.get("wallet_id"); cid = params.get("chain_id")
            resp = await handle_gas_refill(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing wallet_id/chain_id"

        # DISCOVERY
        elif action == "discovery.run":
            src = params.get("source")
            resp = await handle_discovery_run(user_id, [src] if src else [], db)
        elif action == "discovery.sources":
            resp = await handle_discovery_sources(user_id, [], db)
        elif action == "discovery.enable":
            src = params.get("source")
            resp = await handle_discovery_enable(user_id, [src], db) if src else "Missing source"
        elif action == "discovery.disable":
            src = params.get("source")
            resp = await handle_discovery_disable(user_id, [src], db) if src else "Missing source"
        elif action == "discovery.pending":
            resp = await handle_discovery_pending(user_id, [], db)
        elif action == "discovery.set_interval":
            hours = params.get("hours")
            resp = await handle_discovery_set_interval(user_id, [str(hours)], db) if hours else "Missing hours"

        # PROXY
        elif action == "proxy.list":
            resp = await handle_proxy_list(user_id, [], db)
        elif action == "proxy.add":
            url = params.get("url"); ptype = params.get("type")
            resp = await handle_proxy_add(user_id, [url, ptype], db) if url and ptype else "Missing url/type"
        elif action == "proxy.assign":
            wid = params.get("wallet_id"); url = params.get("url")
            resp = await handle_proxy_assign(user_id, [str(wid), url], db) if wid and url else "Missing wallet_id/url"
        elif action == "proxy.unassign":
            wid = params.get("wallet_id")
            resp = await handle_proxy_unassign(user_id, [str(wid)], db) if wid else "Missing wallet_id"
        elif action == "proxy.check":
            wid = params.get("wallet_id")
            resp = await handle_proxy_check(user_id, [str(wid)], db) if wid else "Missing wallet_id"
        elif action == "proxy.rotate":
            wid = params.get("wallet_id")
            resp = await handle_proxy_rotate(user_id, [str(wid)], db) if wid else "Missing wallet_id"
        elif action == "proxy.status":
            resp = await handle_proxy_status(user_id, [], db)

        # ALERT
        elif action == "alert.snooze":
            resp = await handle_alert_snooze(user_id, [str(params.get("minutes", 30))], db)
        elif action == "alert.unsnooze":
            resp = await handle_alert_unsnooze(user_id, [], db)
        elif action == "alert.test":
            resp = await handle_alert_test(user_id, [], db)
        elif action == "alert.list":
            resp = await handle_alert_list(user_id, [], db)
        elif action == "alert.resolve":
            aid = params.get("id")
            resp = await handle_alert_resolve(user_id, [str(aid)], db) if aid else "Missing id"
        elif action == "alert.resolve_all":
            resp = await handle_alert_resolve_all(user_id, [], db)
        elif action == "alert.memory":
            pct = params.get("pct")
            resp = await handle_alert_memory(user_id, [str(pct)], db) if pct else "Missing pct"

        # SYSTEM
        elif action == "system.status":
            resp = await handle_system_status(user_id, [], db)
        elif action == "system.backup":
            resp = await handle_system_backup(user_id, [], db)
        elif action == "system.test_rpc":
            cid = params.get("chain_id")
            resp = await handle_system_test_rpc(user_id, [str(cid)] if cid else [], db)
        elif action == "system.maintenance":
            start = params.get("start"); end = params.get("end")
            resp = await handle_system_maintenance(user_id, [start, end], db) if start and end else "Missing start/end"
        elif action == "system.maintenance_off":
            resp = await handle_system_maintenance_off(user_id, [], db)
        elif action == "system.log_archive":
            resp = await handle_system_log_archive(user_id, [], db)
        elif action == "system.version":
            resp = await handle_system_version(user_id, [], db)

        # HELP / CHAT / CLARIFY
        elif action == "help":
            cat = params.get("category")
            from backend.telegram.commands.help import get_quick_help, get_category_help
            resp = get_category_help(cat) if cat else get_quick_help()
        elif action == "chat":
            reply = params.get("chat_reply") or ""
            resp = reply.strip() if reply.strip() else "Try /help to see what I can do, or just tell me what you need."
        elif action == "clarify":
            needed = params.get("clarification_needed") or "Could you be more specific?"
            resp = f"❓ {needed}"

        else:
            resp = f"⚠️ Action '{action}' not implemented. Try /help"

    except Exception as e:
        logger.exception("dispatch_action failed action=%s", action)
        resp = f"❌ Error in {action}: {str(e)}"

    return resp or "✅ Done."


# -------------------------------------------------------------------
# send_long_message — splits at 4000 chars on newline boundaries
# -------------------------------------------------------------------
async def send_long_message(update, text: str):
    MAX = 4000
    if len(text) <= MAX:
        await update.message.reply_text(text)
        return
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > MAX:
            if chunk.strip():
                await update.message.reply_text(chunk)
            chunk = line + "\n"
        else:
            chunk += line + "\n"
    if chunk.strip():
        await update.message.reply_text(chunk)


# -------------------------------------------------------------------
# Slash command handlers
# -------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized")
        return
    await update.message.reply_text(
        "🤖 Welcome to Musa Ais Airdrop Hunter Agent.\n"
        "Use slash commands or natural language.\n"
        "/help — command categories\n"
        "/commands — full command list"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        return
    from backend.telegram.commands.help import get_quick_help, get_category_help
    category = context.args[0] if context.args else None
    text = get_category_help(category) if category else get_quick_help()
    await update.message.reply_text(text or "Use /commands to see all commands.")


async def commands_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        return
    from backend.telegram.commands.help import get_all_pages
    for page in get_all_pages():
        if page.strip():
            await update.message.reply_text(page)


async def agent_unlock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /agent_unlock <master_password>")
        return
    from backend.database import async_session
    async with async_session() as db:
        response = await handle_agent_unlock(update.effective_user.id, context.args[0], db)
    await update.message.reply_text(response or "✅ Done.")


# -------------------------------------------------------------------
# Natural language fallback
# -------------------------------------------------------------------
async def fallback_nl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        return
    user_id = update.effective_user.id
    raw_text = update.message.text.strip().lower()

    # Handle pending confirmation replies
    if raw_text == "confirm":
        pending = _pop_pending(user_id)
        if not pending:
            await update.message.reply_text("⚠️ Nothing to confirm (or confirmation expired).")
            return
        from backend.database import async_session
        async with async_session() as db:
            resp = await dispatch_action(user_id, pending["action"], pending["params"], db)
        await update.message.reply_text(resp or "✅ Done.")
        return
    if raw_text == "cancel":
        _cancel_pending(user_id)
        await update.message.reply_text("❌ Action cancelled.")
        return

    parsed = await parse_natural_language(update.message.text)
    if parsed.get("action") == "error":
        await update.message.reply_text(f"⚠️ {parsed.get('clarification_needed','Could not parse request.')}")
        return
    # Merge top-level fields into params so dispatch_action can access them.
    # chat_reply and clarification_needed live at the top level of the parsed
    # JSON (siblings of "parameters"), but dispatch_action reads them from params.
    action_params = dict(parsed.get("parameters", {}) or {})
    action = parsed.get("action", "")
    if action == "chat":
        action_params["chat_reply"] = parsed.get("chat_reply") or ""
    elif action == "clarify":
        action_params["clarification_needed"] = parsed.get("clarification_needed") or ""
    from backend.database import async_session
    async with async_session() as db:
        resp = await dispatch_action(user_id, action, action_params, db)
    await update.message.reply_text(resp or "✅ Done.")


# -------------------------------------------------------------------
# Unknown slash command — route through NL parser
# -------------------------------------------------------------------
async def unknown_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        return
    user_id = update.effective_user.id
    text = update.message.text.lstrip("/").replace("_", " ")
    if context.args:
        text = f"{text} {' '.join(context.args)}"
    parsed = await parse_natural_language(text)
    if parsed.get("action") == "error":
        await update.message.reply_text(f"⚠️ {parsed.get('clarification_needed','Unknown command.')}\n\nTry /help")
        return
    # Merge top-level fields into params — same fix as fallback_nl above.
    action_params = dict(parsed.get("parameters", {}) or {})
    action = parsed.get("action", "")
    if action == "chat":
        action_params["chat_reply"] = parsed.get("chat_reply") or ""
    elif action == "clarify":
        action_params["clarification_needed"] = parsed.get("clarification_needed") or ""
    from backend.database import async_session
    async with async_session() as db:
        resp = await dispatch_action(user_id, action, action_params, db)
    await update.message.reply_text(resp or "✅ Done.")


# -------------------------------------------------------------------
# build_bot — registers ALL handlers
# -------------------------------------------------------------------
def build_bot():
    global app
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Core
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("commands", commands_cmd))
    app.add_handler(CommandHandler("agent_unlock", agent_unlock_cmd))

    # All other commands via make_cmd (auto-detects signature)
    handlers = [
        # Wallet
        ("wallet_create", handle_wallet_create),
        ("wallet_list", handle_wallet_list),
        ("wallet_status", handle_wallet_status),
        ("wallet_balance", handle_wallet_balance),
        ("wallet_pause", handle_wallet_pause),
        ("wallet_resume", handle_wallet_resume),
        ("wallet_cooldown", handle_wallet_cooldown),
        ("wallet_blacklist", handle_wallet_blacklist),
        ("wallet_unblacklist", handle_wallet_unblacklist),
        ("wallet_archive", handle_wallet_archive),
        ("wallet_unarchive", handle_wallet_unarchive),
        ("wallet_tag", handle_wallet_tag),
        ("wallet_untag", handle_wallet_untag),
        ("wallet_group", handle_wallet_group),
        ("wallet_fund", handle_wallet_fund),
        ("wallet_health", handle_wallet_health),
        ("wallet_sybil", handle_wallet_sybil),
        ("wallet_persona", handle_wallet_persona),
        ("wallet_top", handle_wallet_top),
        ("wallet_failing", handle_wallet_failing),
        ("wallet_gas_wallets", handle_wallet_gas_wallets),
        ("wallet_set_gas", handle_wallet_set_gas),
        ("wallet_nonce", handle_wallet_nonce),
        # Chain
        ("chain_list", handle_chain_list),
        ("chain_add", handle_chain_add),
        ("chain_enable", handle_chain_enable),
        ("chain_disable", handle_chain_disable),
        ("chain_status", handle_chain_status),
        ("chain_gas", handle_chain_gas),
        ("chain_tokens", handle_chain_tokens),
        ("chain_rpc", handle_chain_rpc),
        ("chain_add_fallback", handle_chain_add_fallback),
        ("chain_remove_fallback", handle_chain_remove_fallback),
        ("chain_test_rpc", handle_chain_test_rpc),
        ("chain_add_token", handle_chain_add_token),
        ("chain_gas_token", handle_chain_gas_token),
        ("chain_set_rate_limit", handle_chain_set_rate_limit),
        # Task
        ("task_list", handle_task_list),
        ("task_status", handle_task_status),
        ("task_enable", handle_task_enable),
        ("task_pause", handle_task_pause),
        ("task_trigger", handle_task_trigger),
        ("task_dry_run", handle_task_dry_run),
        # Project
        ("project_list", handle_project_list),
        ("project_add", handle_project_add),
        ("project_status", handle_project_status),
        ("project_disable", handle_project_disable),
        ("project_enable", handle_project_enable),
        ("project_pause", handle_project_pause),
        ("project_resume", handle_project_resume),
        # Agent
        ("agent_status", handle_agent_status),
        ("agent_start", handle_agent_start),
        ("agent_stop", handle_agent_stop_simple),
        ("agent_pause_all", handle_agent_pause_all),
        ("agent_resume_all", handle_agent_resume_all),
        ("agent_workers", handle_agent_workers),
        ("agent_queue", handle_agent_queue),
        # Faucet
        ("faucet_list", handle_faucet_list),
        ("faucet_request", handle_faucet_request),
        ("faucet_bulk", handle_faucet_bulk),
        # Schedule
        ("schedule_next", handle_schedule_next),
        ("schedule_pause", handle_schedule_pause),
        ("schedule_resume", handle_schedule_resume),
        # Claim
        ("claim_check", handle_claim_check),
        ("claim_eligible", handle_claim_eligible),
        ("claim_value", handle_claim_value),
        ("claim_trigger", handle_claim_trigger),
        ("claim_set_threshold", handle_claim_set_threshold),
        ("claim_auto_on", handle_claim_auto_on),
        ("claim_auto_off", handle_claim_auto_off),
        ("claim_pending", handle_claim_pending),
        ("claim_history", handle_claim_history),
        # Report
        ("report_eligibility", handle_report_eligibility),
        ("report_roi", handle_report_roi),
        ("report_daily_progress", handle_report_daily_progress),
        ("report_gas", handle_report_gas),
        ("report_sybil", handle_report_sybil),
        ("report_activity", handle_report_activity),
        ("report_server", handle_report_server),
        # Config
        ("config_show", handle_config_show),
        ("config_set", handle_config_set),
        ("config_reset", handle_config_reset),
        # AI
        ("ai_log", handle_ai_log),
        ("ai_validate", handle_ai_validate),
        ("ai_approve", handle_ai_approve),
        ("ai_reject", handle_ai_reject),
        ("ai_pending", handle_ai_pending),
        ("ai_status", handle_ai_status),
        ("ai_agreement", handle_ai_agreement),
        # Nonce
        ("nonce_check", handle_nonce_check),
        ("nonce_sync", handle_nonce_sync),
        ("nonce_release", handle_nonce_release),
        ("nonce_release_all", handle_nonce_release_all),
        # TX
        ("tx_stuck", handle_tx_stuck),
        ("tx_speedup", handle_tx_speedup),
        ("tx_cancel", handle_tx_cancel),
        ("tx_status", handle_tx_status),
        ("tx_failed", handle_tx_failed),
        ("tx_verify", handle_tx_verify),
        # Gas
        ("gas_price", handle_gas_price),
        ("gas_spike", handle_gas_spike),
        ("gas_optimal", handle_gas_optimal),
        ("gas_cost", handle_gas_cost),
        ("gas_budget", handle_gas_budget),
        ("gas_refill", handle_gas_refill),
        # Discovery
        ("discovery_run", handle_discovery_run),
        ("discovery_sources", handle_discovery_sources),
        ("discovery_enable", handle_discovery_enable),
        ("discovery_disable", handle_discovery_disable),
        ("discovery_pending", handle_discovery_pending),
        ("discovery_set_interval", handle_discovery_set_interval),
        # Proxy
        ("proxy_list", handle_proxy_list),
        ("proxy_add", handle_proxy_add),
        ("proxy_assign", handle_proxy_assign),
        ("proxy_unassign", handle_proxy_unassign),
        ("proxy_check", handle_proxy_check),
        ("proxy_rotate", handle_proxy_rotate),
        ("proxy_status", handle_proxy_status),
        # Alert
        ("alert_snooze", handle_alert_snooze),
        ("alert_unsnooze", handle_alert_unsnooze),
        ("alert_test", handle_alert_test),
        ("alert_list", handle_alert_list),
        ("alert_resolve", handle_alert_resolve),
        ("alert_resolve_all", handle_alert_resolve_all),
        ("alert_memory", handle_alert_memory),
        # System
        ("system_status", handle_system_status),
        ("system_backup", handle_system_backup),
        ("system_test_rpc", handle_system_test_rpc),
        ("system_maintenance", handle_system_maintenance),
        ("system_maintenance_off", handle_system_maintenance_off),
        ("system_log_archive", handle_system_log_archive),
        ("system_version", handle_system_version),
    ]

    for cmd_name, handler_fn in handlers:
        app.add_handler(CommandHandler(cmd_name, make_cmd(handler_fn)))

    # Catch-all: unrecognised slash → NL parser
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command_handler))
    # Free text → NL parser
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_nl))

    set_bot_app(app)
    return app


async def start_bot():
    bot_app = build_bot()
    await bot_app.initialize()
    await bot_app.bot.set_my_commands([
        ("agent_status",        "Agent status + worker slots"),
        ("agent_start",         "Start the agent"),
        ("agent_stop",          "Graceful stop ⚠️"),
        ("agent_unlock",        "Unlock seed with password"),
        ("agent_workers",       "Live worker slot view"),
        ("wallet_list",         "List all wallets"),
        ("wallet_create",       "Generate HD wallets"),
        ("wallet_balance",      "Wallet balances"),
        ("wallet_pause",        "Pause wallet(s) ⚠️"),
        ("wallet_resume",       "Resume wallet(s)"),
        ("wallet_health",       "Wallet health score"),
        ("wallet_failing",      "Show failing wallets"),
        ("project_list",        "List all projects"),
        ("project_add",         "Add a project"),
        ("project_status",      "Project eligibility"),
        ("task_list",           "List task configs"),
        ("task_trigger",        "Trigger a task now"),
        ("chain_list",          "List chains"),
        ("chain_status",        "Chain RPC + gas"),
        ("faucet_request",      "Request faucet tokens"),
        ("faucet_bulk",         "Bulk faucet all wallets"),
        ("report_eligibility",  "Eligibility progress"),
        ("report_daily_progress","Daily tx vs target"),
        ("report_server",       "Server RAM/CPU/workers"),
        ("report_roi",          "ROI report"),
        ("gas_price",           "Current gas price"),
        ("tx_stuck",            "List stuck transactions"),
        ("nonce_release_all",   "Release all stuck nonces ⚠️"),
        ("config_show",         "Show wallet settings"),
        ("config_set",          "Change a setting"),
        ("discovery_pending",   "Projects awaiting approval"),
        ("claim_check",         "Scan for claimable airdrops"),
        ("system_status",       "Full system health"),
        ("system_version",      "Version + uptime"),
        ("ai_status",           "Groq + Gemini API status"),
        ("alert_list",          "Active alerts"),
        ("help",                "Help — /help [category]"),
        ("commands",            "Send all command categories"),
        ("start",               "Start the bot"),
    ])
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("Telegram bot started successfully")
    return bot_app

