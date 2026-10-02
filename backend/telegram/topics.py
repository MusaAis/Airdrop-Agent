"""
Telegram group + topic routing (PLAN.md Phase 8).

One private supergroup with Topics enabled replaces the DM-only firehose:
  📊 Daily report · 🗓 Weekly summary · 📅 Monthly summary
  🚨 Errors · 🤖 AI activity · 🔔 Alerts

The group and topic ids are stored in the DB (table telegram_routes), created
by `/group_setup` run inside the group, so no .env editing is needed. If no
group is configured (or a send to it fails) messages fall back to DMs to the
whitelisted users, exactly as before Phase 8.

The table is registered on the shared Base; main.py imports this module before
init_db() so create_all() creates it. No migration needed.
"""
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, delete, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base, async_session

logger = logging.getLogger("airdrop.telegram.topics")


class TelegramRoute(Base):
    """Key/value: 'group_chat_id' and 'topic:<key>' -> message_thread_id."""
    __tablename__ = "telegram_routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


# (key, topic title)
TOPICS: List[Tuple[str, str]] = [
    ("daily", "📊 Daily report"),
    ("weekly", "🗓 Weekly summary"),
    ("monthly", "📅 Monthly summary"),
    ("errors", "🚨 Errors"),
    ("ai", "🤖 AI activity"),
    ("alerts", "🔔 Alerts"),
]

# alert `type` (see create_and_send_alert) -> topic key
_ALERT_TOPIC = {
    "failure_cluster": "errors",
    "ai_action": "ai",
}

_cache: Optional[Dict[str, str]] = None


async def _routes(force: bool = False) -> Dict[str, str]:
    global _cache
    if _cache is None or force:
        async with async_session() as db:
            rows = (await db.execute(select(TelegramRoute))).scalars().all()
        _cache = {r.key: r.value for r in rows}
    return _cache


async def _set(key: str, value: str) -> None:
    async with async_session() as db:
        row = (await db.execute(select(TelegramRoute).where(TelegramRoute.key == key))).scalar_one_or_none()
        if row:
            row.value = value
        else:
            db.add(TelegramRoute(key=key, value=value))
        await db.commit()
    (await _routes())[key] = value


async def _clear_topics() -> None:
    async with async_session() as db:
        await db.execute(delete(TelegramRoute).where(TelegramRoute.key.like("topic:%")))
        await db.commit()
    await _routes(force=True)


async def resolve_route(topic: str) -> Optional[Tuple[int, int]]:
    """(group_chat_id, message_thread_id) for a topic key, or None if not configured."""
    r = await _routes()
    gid, tid = r.get("group_chat_id"), r.get(f"topic:{topic}")
    if gid and tid:
        return int(gid), int(tid)
    return None


def topic_for_alert(alert_type: str, severity: str) -> str:
    """Unmapped alert types go to 🔔 Alerts, except critical ones, which go to 🚨 Errors."""
    t = _ALERT_TOPIC.get(alert_type)
    if t:
        return t
    return "errors" if severity == "critical" else "alerts"


async def setup_topics(bot, chat_id: int, reset: bool = False) -> List[Tuple[str, str]]:
    """Create any missing topics in the group and remember the ids.
    Returns [(title, 'created' | 'exists' | 'error: ...')]."""
    r = await _routes()
    if reset or (r.get("group_chat_id") and int(r["group_chat_id"]) != chat_id):
        await _clear_topics()
    await _set("group_chat_id", str(chat_id))
    r = await _routes()
    out = []
    for key, title in TOPICS:
        if r.get(f"topic:{key}"):
            out.append((title, "exists"))
            continue
        try:
            topic = await bot.create_forum_topic(chat_id=chat_id, name=title)
            await _set(f"topic:{key}", str(topic.message_thread_id))
            out.append((title, "created"))
        except Exception as e:
            logger.error("create_forum_topic %s failed: %s", key, e)
            out.append((title, f"error: {str(e)[:120]}"))
    return out


async def route_status() -> dict:
    r = await _routes()
    return {
        "group_chat_id": r.get("group_chat_id"),
        "topics": {k: r.get(f"topic:{k}") for k, _ in TOPICS},
    }
