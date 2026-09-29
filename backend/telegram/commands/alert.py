import logging
from datetime import datetime, timezone, timedelta
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.alert")

# In-memory snooze state
_snoozed = False
_snooze_until = None


def is_snoozed() -> bool:
    """Live getter used by create_and_send_alert (Phase 5). Expires on its own."""
    global _snoozed, _snooze_until
    if not _snoozed:
        return False
    if _snooze_until and datetime.now(timezone.utc) >= _snooze_until:
        _snoozed = False
        _snooze_until = None
        return False
    return True


def set_snooze(minutes: int) -> datetime:
    """Shared by the Telegram handler and the website API (Phase 5 follow-up)."""
    global _snoozed, _snooze_until
    _snoozed = True
    _snooze_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return _snooze_until


def clear_snooze() -> None:
    global _snoozed, _snooze_until
    _snoozed = False
    _snooze_until = None


def snooze_until():
    """Returns the expiry datetime if snoozed, else None."""
    return _snooze_until if is_snoozed() else None


async def handle_alert_snooze(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    mins = int(args[0]) if args else 30
    until = set_snooze(mins)
    return f"🔕 Non-critical alerts snoozed for {mins} minutes (until {until.strftime('%H:%M')} UTC)."


async def handle_alert_unsnooze(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    clear_snooze()
    return "🔔 All alerts re-enabled."


async def handle_alert_test(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    try:
        from backend.telegram.alerts import create_and_send_alert
        await create_and_send_alert("test", "info", "🔔 Test alert from Telegram — alerts are working!")
        return "✅ Test alert sent."
    except Exception as e:
        return f"❌ Alert send failed: {e}"


async def handle_alert_list(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import Alert
    from sqlalchemy import select, desc
    alerts = (await db.execute(
        select(Alert).where(Alert.resolved == False).order_by(desc(Alert.created_at)).limit(15)
    )).scalars().all()
    if not alerts:
        return "✅ No unresolved alerts."
    lines = [f"🔔 Unresolved Alerts ({len(alerts)}):"]
    for a in alerts:
        icon = "🔴" if a.severity == "critical" else "🟡" if a.severity == "warning" else "ℹ️"
        lines.append(f"{icon} ID {a.id}: [{a.type}] {a.message[:60]}")
    return "\n".join(lines)


async def handle_alert_resolve(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: /alert_resolve <id>"
    from backend.models import Alert
    alert = await db.get(Alert, int(args[0]))
    if not alert: return f"Alert {args[0]} not found."
    alert.resolved = True
    await db.commit()
    return f"✅ Alert {args[0]} resolved."


async def handle_alert_resolve_all(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    from backend.models import Alert
    from sqlalchemy import update
    await db.execute(update(Alert).values(resolved=True))
    await db.commit()
    return "✅ All alerts marked resolved."


async def handle_alert_memory(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: /alert_memory <pct> (e.g. 85)"
    try:
        pct = float(args[0])
        if not (50 <= pct <= 99):
            return "Threshold must be between 50 and 99."
        import backend.core.memory_guard as mg
        mg.MEMORY_CRITICAL_PCT = pct
        return f"✅ RAM alert threshold set to {pct}%."
    except Exception as e:
        return f"❌ Error: {e}"
