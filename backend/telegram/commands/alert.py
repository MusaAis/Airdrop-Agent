import logging
from backend.telegram.whitelist import is_whitelisted

logger = logging.getLogger("airdrop.tg.alert")

# In-memory snooze state
_snoozed = False
_snooze_until = None


async def handle_alert_snooze(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    global _snoozed, _snooze_until
    from datetime import datetime, timezone, timedelta
    mins = int(args[0]) if args else 30
    _snoozed = True
    _snooze_until = datetime.now(timezone.utc) + timedelta(minutes=mins)
    return f"🔕 Non-critical alerts snoozed for {mins} minutes (until {_snooze_until.strftime('%H:%M')} UTC)."


async def handle_alert_unsnooze(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    global _snoozed, _snooze_until
    _snoozed = False
    _snooze_until = None
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
