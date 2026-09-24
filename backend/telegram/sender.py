import logging
from typing import Optional
from backend.config import ALLOWED_USER_IDS

logger = logging.getLogger("airdrop.telegram.sender")

_bot_app = None  # set by bot.py after build


def set_bot_app(app):
    global _bot_app
    _bot_app = app


def get_bot_app():
    return _bot_app


async def send_telegram_message(
    text: str,
    parse_mode: Optional[str] = "Markdown",
    chat_id: Optional[int] = None,
):
    """
    Send a message to all whitelisted user IDs, or a specific chat_id.
    parse_mode: "Markdown", "HTML", or None.
    """
    app = get_bot_app()
    if not app or not app.bot:
        logger.warning("Telegram bot not ready — message not sent")
        return

    targets = [chat_id] if chat_id else [int(uid) for uid in ALLOWED_USER_IDS if uid]

    for uid in targets:
        try:
            await app.bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode=parse_mode,
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram to {uid}: {e}")
