import logging
import inspect
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from backend.config import TELEGRAM_BOT_TOKEN
from backend.telegram.whitelist import is_whitelisted
from backend.telegram.nl_parser import parse_natural_language
from backend.telegram.project_wizard import has_active_wizard, handle_wizard_reply
from backend.telegram.entity_resolver import resolve_entities
from backend.telegram.conversation import record_turn
from backend.telegram.commands.wallet import (
    handle_wallet_create, handle_wallet_list, handle_wallet_status,
    handle_wallet_balance, handle_wallet_pause, handle_wallet_resume,
    handle_wallet_blacklist, handle_wallet_archive, handle_wallet_tag,
    handle_wallet_group, handle_wallet_fund,
    handle_wallet_health, handle_wallet_sybil,
    handle_wallet_top, handle_wallet_failing,
    handle_wallet_set_gas,
)
from backend.telegram.commands.chain import (
    handle_chain_list, handle_chain_add, handle_chain_enable, handle_chain_disable,
    handle_chain_status, handle_chain_gas, handle_chain_tokens,
    handle_chain_add_token,
)
from backend.telegram.commands.task import (
    handle_task_list, handle_task_status, handle_task_enable, handle_task_pause,
    handle_task_trigger,
)
from backend.telegram.commands.project import (
    handle_project_list, handle_project_add, handle_project_status,
    handle_project_disable, handle_project_enable, handle_project_pause, handle_project_resume,
    handle_project_approve, handle_project_reject,
    handle_project_gap, handle_project_reset_circuit,
)
from backend.telegram.commands.faucet import (
    handle_faucet_request, handle_faucet_bulk,
)
from backend.telegram.commands.report import (
    handle_report_eligibility, handle_report_daily_progress,
    handle_report_gas, handle_report_server, handle_report_summary,
)
from backend.telegram.commands.config import (
    handle_config_set, handle_config_show,
)
from backend.telegram.commands.agent_extras import (
    handle_agent_start, handle_agent_stop, handle_agent_pause_all,
    handle_agent_resume_all,
)
from backend.telegram.commands.claim import (
    handle_claim_check, handle_claim_eligible,
    handle_claim_trigger, handle_claim_pending,
)
from backend.telegram.commands.ai import (
    handle_ai_pending, handle_ai_approve, handle_ai_reject, handle_ai_status,
    handle_ai_autonomy_off, handle_ai_autonomy_on,
)
from backend.telegram.commands.nonce import (
    handle_nonce_release_all,
)
from backend.telegram.commands.tx import (
    handle_tx_stuck, handle_tx_speedup, handle_tx_cancel,
)
from backend.telegram.commands.gas import (
    handle_gas_price, handle_gas_refill,
)
from backend.telegram.commands.alert import (
    handle_alert_list, handle_alert_resolve_all,
)
from backend.telegram.commands.system import (
    handle_system_status, handle_system_version,
)
from backend.telegram.commands.agent import (
    handle_agent_status, handle_agent_stop as handle_agent_stop_simple, handle_agent_unlock,
    handle_agent_kill, handle_agent_dryrun_on, handle_agent_dryrun_off,
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
    "nonce.release_all",
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
                "nonce.release_all": "⚠️ Release all nonce locks",
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
        elif action == "wallet.blacklist":
            wid = params.get("id")
            resp = await handle_wallet_blacklist(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.archive":
            wid = params.get("id")
            resp = await handle_wallet_archive(user_id, [str(wid)], db) if wid else "Missing id"
        elif action == "wallet.tag":
            wid = params.get("id"); tag = params.get("tag")
            resp = await handle_wallet_tag(user_id, [str(wid), tag], db) if wid and tag else "Missing id/tag"
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
        elif action == "wallet.top":
            resp = await handle_wallet_top(user_id, [str(params.get("n", 10))], db)
        elif action == "wallet.failing":
            resp = await handle_wallet_failing(user_id, [], db)
        elif action == "wallet.set_gas":
            wid = params.get("id"); val = params.get("value", "true")
            resp = await handle_wallet_set_gas(user_id, [str(wid), str(val)], db) if wid else "Missing id"

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
        elif action == "chain.add_token":
            cid = params.get("chain_id"); sym = params.get("symbol"); addr = params.get("address"); dec = params.get("decimals")
            resp = await handle_chain_add_token(user_id, [str(cid), sym, addr, str(dec)], db) if all([cid,sym,addr,dec]) else "Missing args"

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
        elif action == "project.approve":
            resp = await handle_project_approve(user_id, [str(params.get("id",""))], db)
        elif action == "project.reject":
            resp = await handle_project_reject(user_id, [str(params.get("id",""))], db)
        elif action == "project.gap":
            resp = await handle_project_gap(user_id, [str(params.get("id",""))], db)
        elif action == "project.reset_circuit":
            resp = await handle_project_reset_circuit(user_id, [str(params.get("id",""))], db)

        # FAUCET
        elif action == "faucet.request":
            wid = params.get("wallet_id"); cid = params.get("chain_id")
            resp = await handle_faucet_request(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing wallet_id/chain_id"
        elif action == "faucet.bulk":
            cid = params.get("chain_id")
            resp = await handle_faucet_bulk(user_id, [str(cid)] if cid else [], db)

        # CLAIM
        elif action == "claim.check":
            resp = await handle_claim_check(user_id, [], db)
        elif action == "claim.eligible":
            resp = await handle_claim_eligible(user_id, [], db)
        elif action == "claim.trigger":
            wid = params.get("wallet_id"); pid = params.get("project_id")
            resp = await handle_claim_trigger(user_id, [str(wid), str(pid)], db) if wid and pid else "Missing wallet_id/project_id"
        elif action == "claim.pending":
            resp = await handle_claim_pending(user_id, [], db)

        # REPORT
        elif action == "report.eligibility":
            pid = params.get("project_id")
            resp = await handle_report_eligibility(user_id, [str(pid)] if pid else [], db)
        elif action == "report.daily_progress":
            pid = params.get("project_id")
            resp = await handle_report_daily_progress(user_id, [str(pid)] if pid else [], db)
        elif action == "report.gas":
            cid = params.get("chain_id")
            resp = await handle_report_gas(user_id, [str(cid)] if cid else [], db)
        elif action == "report.server":
            resp = await handle_report_server(user_id, [], db)
        elif action == "report.summary":
            hours = params.get("hours")
            resp = await handle_report_summary(user_id, [str(hours)] if hours else [], db)

        # CONFIG
        elif action == "config.show":
            resp = await handle_config_show(user_id, [str(params.get("wallet_id","all"))], db)
        elif action == "config.set":
            key = params.get("key"); val = params.get("value"); wid = params.get("wallet_id","all")
            resp = await handle_config_set(user_id, [str(wid), str(key), str(val)], db) if key and val else "Missing key/value"

        # AI
        elif action == "ai.pending":
            resp = await handle_ai_pending(user_id, [], db)
        elif action == "ai.approve":
            vid = params.get("validation_id")
            resp = await handle_ai_approve(user_id, [str(vid)], db) if vid else "Missing validation_id"
        elif action == "ai.reject":
            vid = params.get("validation_id")
            resp = await handle_ai_reject(user_id, [str(vid)], db) if vid else "Missing validation_id"
        elif action == "ai.status":
            resp = await handle_ai_status(user_id, [], db)
        elif action == "ai.autonomy_off":
            resp = await handle_ai_autonomy_off(user_id, [], db)
        elif action == "ai.autonomy_on":
            resp = await handle_ai_autonomy_on(user_id, [], db)

        # NONCE
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

        # GAS
        elif action == "gas.price":
            cid = params.get("chain_id")
            resp = await handle_gas_price(user_id, [str(cid)], db) if cid else "Missing chain_id"
        elif action == "gas.refill":
            wid = params.get("wallet_id"); cid = params.get("chain_id")
            resp = await handle_gas_refill(user_id, [str(wid), str(cid)], db) if wid and cid else "Missing wallet_id/chain_id"

        # ALERT
        elif action == "alert.list":
            resp = await handle_alert_list(user_id, [], db)
        elif action == "alert.resolve_all":
            resp = await handle_alert_resolve_all(user_id, [], db)

        # SYSTEM
        elif action == "system.status":
            resp = await handle_system_status(user_id, [], db)
        elif action == "system.version":
            resp = await handle_system_version(user_id, [], db)

        # AGENT
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
        elif action == "agent.kill":
            resp = await handle_agent_kill(user_id, db)
        elif action == "agent.dryrun":
            resp = await handle_agent_dryrun_on(user_id, db)
        elif action == "agent.dryrun_off":
            resp = await handle_agent_dryrun_off(user_id, db)
        elif action == "agent.unlock":
            # Never reachable via NL parsing — prompt_telegram_cmd forbids
            # routing to this action (see Phase 4 note in ai/prompts.py).
            # Kept here only so a stray/legacy call doesn't hard-crash.
            resp = "⚠️ Use the dedicated /agent_unlock <password> command — never send your master password as a chat message."

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
# report_summary_cmd — direct slash command (bypasses NL parser entirely,
# same as any other curated command; also reachable via NL as report.summary)
# -------------------------------------------------------------------
async def report_summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized")
        return
    from backend.database import async_session
    async with async_session() as db:
        try:
            response = await handle_report_summary(update.effective_user.id, context.args or [], db)
        except Exception as e:
            logger.exception("report_summary_cmd failed: %s", e)
            response = f"❌ Error: {e}"
    await send_long_message(update, response or "✅ Done.")


# -------------------------------------------------------------------
# Natural language fallback
# -------------------------------------------------------------------
async def _parse_and_dispatch_nl(user_id: int, raw_text: str, db) -> str:
    """
    Shared by fallback_nl and unknown_command_handler (Phase 4): runs the NL
    parser with conversation context + entity index, resolves any fuzzy
    entity references in the result, and records the turn for future context.
    Extracted into one function so both callers get identical Phase 4
    behavior instead of two copies drifting apart.
    """
    parsed = await parse_natural_language(raw_text, db=db, user_id=user_id)
    if parsed.get("action") == "error":
        return f"⚠️ {parsed.get('clarification_needed','Could not parse request.')}"

    action_params = dict(parsed.get("parameters", {}) or {})
    action = parsed.get("action", "")
    if action == "chat":
        action_params["chat_reply"] = parsed.get("chat_reply") or ""
    elif action == "clarify":
        action_params["clarification_needed"] = parsed.get("clarification_needed") or ""

    # Phase 4: fuzzy entity resolution — turn "my main wallet" style params
    # into real numeric ids, or downgrade to a clarify message if ambiguous.
    resolved = await resolve_entities(db, action, action_params)
    if "_clarify" in resolved:
        resp = f"❓ {resolved['_clarify']}"
        record_turn(user_id, raw_text, "clarify", {}, reply_summary=resp)
        return resp
    action_params = resolved

    resp = await dispatch_action(user_id, action, action_params, db)
    record_turn(user_id, raw_text, action, action_params, reply_summary=resp)
    return resp


async def fallback_nl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        return
    user_id = update.effective_user.id
    raw_text = update.message.text.strip()

    # Guided /project_add wizard takes priority over both the pending-
    # confirmation flow and NL parsing while it's active for this user, so a
    # wizard reply like "yes"/"no"/"skip"/"confirm" is never mistaken for a
    # destructive-action confirmation (or vice versa).
    if has_active_wizard(user_id):
        from backend.database import async_session
        async with async_session() as db:
            resp = await handle_wizard_reply(user_id, raw_text, db)
        await update.message.reply_text(resp or "✅ Done.")
        return

    raw_text_lower = raw_text.lower()

    # Handle pending confirmation replies
    if raw_text_lower == "confirm":
        pending = _pop_pending(user_id)
        if not pending:
            await update.message.reply_text("⚠️ Nothing to confirm (or confirmation expired).")
            return
        from backend.database import async_session
        async with async_session() as db:
            resp = await dispatch_action(user_id, pending["action"], pending["params"], db)
        await update.message.reply_text(resp or "✅ Done.")
        return
    if raw_text_lower == "cancel":
        _cancel_pending(user_id)
        await update.message.reply_text("❌ Action cancelled.")
        return

    from backend.database import async_session
    async with async_session() as db:
        resp = await _parse_and_dispatch_nl(user_id, raw_text, db)
    await send_long_message(update, resp or "✅ Done.")


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
    from backend.database import async_session
    async with async_session() as db:
        resp = await _parse_and_dispatch_nl(user_id, text, db)
    await send_long_message(update, resp or "✅ Done.")


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
    app.add_handler(CommandHandler("report_summary", report_summary_cmd))

    # All other commands via make_cmd (auto-detects signature)
    handlers = [
        # Wallet
        ("wallet_create", handle_wallet_create),
        ("wallet_list", handle_wallet_list),
        ("wallet_status", handle_wallet_status),
        ("wallet_balance", handle_wallet_balance),
        ("wallet_pause", handle_wallet_pause),
        ("wallet_resume", handle_wallet_resume),
        ("wallet_blacklist", handle_wallet_blacklist),
        ("wallet_archive", handle_wallet_archive),
        ("wallet_tag", handle_wallet_tag),
        ("wallet_group", handle_wallet_group),
        ("wallet_fund", handle_wallet_fund),
        ("wallet_health", handle_wallet_health),
        ("wallet_sybil", handle_wallet_sybil),
        ("wallet_top", handle_wallet_top),
        ("wallet_failing", handle_wallet_failing),
        ("wallet_set_gas", handle_wallet_set_gas),
        # Chain
        ("chain_list", handle_chain_list),
        ("chain_add", handle_chain_add),
        ("chain_enable", handle_chain_enable),
        ("chain_disable", handle_chain_disable),
        ("chain_status", handle_chain_status),
        ("chain_gas", handle_chain_gas),
        ("chain_tokens", handle_chain_tokens),
        ("chain_add_token", handle_chain_add_token),
        # Task
        ("task_list", handle_task_list),
        ("task_status", handle_task_status),
        ("task_enable", handle_task_enable),
        ("task_pause", handle_task_pause),
        ("task_trigger", handle_task_trigger),
        # Project
        ("project_list", handle_project_list),
        ("project_add", handle_project_add),
        ("project_status", handle_project_status),
        ("project_disable", handle_project_disable),
        ("project_enable", handle_project_enable),
        ("project_pause", handle_project_pause),
        ("project_resume", handle_project_resume),
        ("project_approve", handle_project_approve),
        ("project_reject", handle_project_reject),
        ("project_gap", handle_project_gap),
        ("project_reset_circuit", handle_project_reset_circuit),
        # Agent
        ("agent_status", handle_agent_status),
        ("agent_start", handle_agent_start),
        ("agent_stop", handle_agent_stop_simple),
        ("agent_pause_all", handle_agent_pause_all),
        ("agent_resume_all", handle_agent_resume_all),
        # Faucet
        ("faucet_request", handle_faucet_request),
        ("faucet_bulk", handle_faucet_bulk),
        # Claim
        ("claim_check", handle_claim_check),
        ("claim_eligible", handle_claim_eligible),
        ("claim_trigger", handle_claim_trigger),
        ("claim_pending", handle_claim_pending),
        # Report
        ("report_eligibility", handle_report_eligibility),
        ("report_daily_progress", handle_report_daily_progress),
        ("report_gas", handle_report_gas),
        ("report_server", handle_report_server),
        # Config
        ("config_show", handle_config_show),
        ("config_set", handle_config_set),
        # AI
        ("ai_pending", handle_ai_pending),
        ("ai_approve", handle_ai_approve),
        ("ai_reject", handle_ai_reject),
        ("ai_status", handle_ai_status),
        ("ai_autonomy_off", handle_ai_autonomy_off),
        ("ai_autonomy_on", handle_ai_autonomy_on),
        # Nonce
        ("nonce_release_all", handle_nonce_release_all),
        # TX
        ("tx_stuck", handle_tx_stuck),
        ("tx_speedup", handle_tx_speedup),
        ("tx_cancel", handle_tx_cancel),
        # Gas
        ("gas_price", handle_gas_price),
        ("gas_refill", handle_gas_refill),
        # Alert
        ("alert_list", handle_alert_list),
        ("alert_resolve_all", handle_alert_resolve_all),
        # System
        ("system_status", handle_system_status),
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
        ("wallet_list",         "List all wallets"),
        ("wallet_create",       "Generate HD wallets"),
        ("wallet_balance",      "Wallet balances"),
        ("wallet_pause",        "Pause wallet(s) ⚠️"),
        ("wallet_resume",       "Resume wallet(s)"),
        ("wallet_health",       "Wallet health score"),
        ("wallet_failing",      "Show failing wallets"),
        ("project_list",        "List all projects"),
        ("project_add",         "Add a project (guided setup)"),
        ("project_status",      "Project eligibility + status"),
        ("project_approve",     "AI-review and activate a project"),
        ("task_list",           "List task configs"),
        ("task_trigger",        "Trigger a task now"),
        ("chain_list",          "List chains"),
        ("chain_status",        "Chain RPC + gas"),
        ("faucet_request",      "Request faucet tokens"),
        ("faucet_bulk",         "Bulk faucet all wallets"),
        ("claim_check",         "Scan for claimable airdrops"),
        ("claim_trigger",       "Manually execute a claim ⚠️"),
        ("report_eligibility",  "Eligibility progress"),
        ("report_daily_progress","Daily tx vs target"),
        ("report_server",       "Server RAM/CPU/workers"),
        ("report_summary",      "AI-narrated summary"),
        ("gas_price",           "Current gas price"),
        ("tx_stuck",            "List stuck transactions"),
        ("nonce_release_all",   "Release all stuck nonces ⚠️"),
        ("config_show",         "Show wallet settings"),
        ("config_set",          "Change a setting"),
        ("system_status",       "Full system health"),
        ("ai_status",           "Groq + Gemini API status"),
        ("ai_autonomy_off",     "Freeze AI autonomous management ⚠️"),
        ("alert_list",          "Active alerts"),
        ("help",                "Help — /help [category]"),
        ("commands",            "Send all command categories"),
        ("start",               "Start the bot"),
    ])
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("Telegram bot started successfully")
    return bot_app
