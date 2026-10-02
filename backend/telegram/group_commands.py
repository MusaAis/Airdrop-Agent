"""
Telegram commands for Phase 8 group/topic routing. Registered from bot.py via
register_group_handlers(app) (before the catch-all handlers).

  /group_setup [reset]   run INSIDE the group: creates the report topics
  /group_status          show where reports are going
  /report_now [kind]     send a report now: daily | weekly | monthly | ai
"""
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from backend.telegram.whitelist import is_whitelisted
from backend.telegram import topics

logger = logging.getLogger("airdrop.tg.group")

_KINDS = ("daily", "weekly", "monthly", "ai")


async def group_setup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized")
        return
    chat = update.effective_chat
    if chat.type != "supergroup" or not getattr(chat, "is_forum", False):
        await update.message.reply_text(
            "Run this inside your private group, after turning on Topics:\n"
            "1. Create a group and add this bot\n"
            "2. Group settings → Topics → enable (this makes it a supergroup)\n"
            "3. Make the bot an admin with the 'Manage topics' permission\n"
            "4. Send /group_setup in the group"
        )
        return
    reset = bool(context.args) and context.args[0].lower() == "reset"
    results = await topics.setup_topics(context.bot, chat.id, reset=reset)
    lines = ["🧩 Group routing set up:"] + [f"{t}: {r}" for t, r in results]
    if any(r.startswith("error") for _, r in results):
        lines.append("\nIf a topic failed, check the bot is admin with 'Manage topics', then run /group_setup again.")
    else:
        lines.append("\nReports and alerts now go to these topics. Keep this group private.")
    await update.message.reply_text("\n".join(lines))


async def group_status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized")
        return
    st = await topics.route_status()
    if not st["group_chat_id"]:
        await update.message.reply_text("No group configured — messages go to DMs. Run /group_setup inside your group.")
        return
    lines = [f"Group: {st['group_chat_id']}"] + [
        f"{title}: {'thread ' + st['topics'][key] if st['topics'].get(key) else 'not created'}"
        for key, title in topics.TOPICS
    ]
    await update.message.reply_text("\n".join(lines))


async def report_now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_whitelisted(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized")
        return
    kind = (context.args[0].lower() if context.args else "daily")
    if kind not in _KINDS:
        await update.message.reply_text(f"Usage: /report_now [{'|'.join(_KINDS)}]")
        return
    try:
        if kind == "ai":
            from backend.reports.periodic import send_ai_report
            await send_ai_report()
        else:
            from backend.reports.periodic import send_period_report
            await send_period_report(kind)
        await update.message.reply_text(f"✅ {kind} report sent.")
    except Exception as e:
        logger.exception("report_now failed")
        await update.message.reply_text(f"❌ Could not send report: {e}")


def register_group_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("group_setup", group_setup_cmd))
    app.add_handler(CommandHandler("group_status", group_status_cmd))
    app.add_handler(CommandHandler("report_now", report_now_cmd))
