import logging
from typing import List, Optional
from backend.config import ALLOWED_USER_IDS

logger = logging.getLogger("airdrop.telegram.sender")

_bot_app = None  # set by bot.py after build
_MAX_LEN = 4000  # Telegram limit is 4096


def set_bot_app(app):
    global _bot_app
    _bot_app = app


def get_bot_app():
    return _bot_app


def _chunks(text: str) -> List[str]:
    if len(text) <= _MAX_LEN:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > _MAX_LEN:           # a single huge line
            if cur:
                out.append(cur); cur = ""
            out.append(line[:_MAX_LEN]); line = line[_MAX_LEN:]
        if len(cur) + len(line) + 1 > _MAX_LEN:
            out.append(cur); cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


async def _send_one(bot, chat_id, text: str, parse_mode: Optional[str], thread_id: Optional[int] = None) -> bool:
    kwargs = {"chat_id": chat_id, "text": text}
    if thread_id:
        kwargs["message_thread_id"] = thread_id
    try:
        await bot.send_message(parse_mode=parse_mode, **kwargs)
        return True
    except Exception as e:
        # Markdown from alert text can be malformed — retry once as plain text
        if parse_mode and "parse entities" in str(e).lower():
            try:
                await bot.send_message(**kwargs)
                return True
            except Exception as e2:
                e = e2
        logger.error(f"Failed to send Telegram to {chat_id} (thread {thread_id}): {e}")
        return False


async def send_telegram_message(
    text: str,
    parse_mode: Optional[str] = "Markdown",
    chat_id: Optional[int] = None,
    topic: Optional[str] = None,
):
    """
    Send to the configured group topic if `topic` is given and the group is set
    up (see telegram/topics.py); otherwise, or if that send fails, DM every
    whitelisted user (or just `chat_id`). parse_mode: "Markdown", "HTML", or None.
    """
    app = get_bot_app()
    if not app or not app.bot:
        logger.warning("Telegram bot not ready — message not sent")
        return

    parts = _chunks(text)

    if topic and chat_id is None:
        from backend.telegram.topics import resolve_route
        route = await resolve_route(topic)
        if route:
            gid, tid = route
            if await _send_one(app.bot, gid, parts[0], parse_mode, tid):
                for p in parts[1:]:
                    await _send_one(app.bot, gid, p, parse_mode, tid)
                return
            logger.warning(f"Group topic '{topic}' send failed — falling back to DMs")

    targets = [chat_id] if chat_id else [int(uid) for uid in ALLOWED_USER_IDS if uid]
    for uid in targets:
        for p in parts:
            await _send_one(app.bot, uid, p, parse_mode)
