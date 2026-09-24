import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Proxy
from backend.proxy_manager import get_assigned_proxy, rotate_proxy
from backend.telegram.whitelist import is_whitelisted

async def handle_proxy_list(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    proxies = (await db.execute(select(Proxy))).scalars().all()
    if not proxies: return "No proxies configured."
    return "\n".join(f"{p.id}: {p.url} type:{p.type} assigned wallet:{p.wallet_id} active:{p.is_active}" for p in proxies)

async def handle_proxy_add(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: proxy.add <url> <type>"
    proxy = Proxy(url=args[0], type=args[1], is_active=True)
    db.add(proxy)
    await db.commit()
    return f"Proxy added (ID:{proxy.id})."

async def handle_proxy_assign(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if len(args)<2: return "Usage: proxy.assign <wallet_id> <proxy_url>"
    wid = int(args[0])
    url = args[1]
    proxy = (await db.execute(select(Proxy).where(Proxy.url==url))).scalar_one_or_none()
    if not proxy: return "Proxy not found."
    proxy.wallet_id = wid
    await db.commit()
    return f"Proxy assigned to wallet {wid}."

async def handle_proxy_unassign(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: proxy.unassign <wallet_id>"
    wid = int(args[0])
    proxies = (await db.execute(select(Proxy).where(Proxy.wallet_id==wid))).scalars().all()
    for p in proxies:
        p.wallet_id = None
    await db.commit()
    return f"Removed proxy from wallet {wid}."

async def handle_proxy_check(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: proxy.check <wallet_id>"
    wid = int(args[0])
    proxy = await get_assigned_proxy(wid)
    if not proxy: return "No proxy assigned to this wallet."
    return f"Proxy for wallet {wid}: {proxy['http']}"

async def handle_proxy_rotate(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    if not args: return "Usage: proxy.rotate <wallet_id>"
    wid = int(args[0])
    new_url = await rotate_proxy(wid)
    if new_url:
        return f"Rotated to proxy: {new_url}"
    return "No other proxy available."

async def handle_proxy_status(user_id, args, db, confirmation=None):
    if not is_whitelisted(user_id): return "⛔ Unauthorized"
    proxies = (await db.execute(select(Proxy))).scalars().all()
    if not proxies: return "No proxies."
    return "\n".join(f"{p.id}: active={p.is_active} wallet={p.wallet_id}" for p in proxies)
