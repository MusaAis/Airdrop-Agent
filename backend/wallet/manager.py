from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models import Wallet, WalletSettings
from backend.wallet.hd_generator import generate_wallets
from backend.wallet.crypto import encrypt_private_key
from typing import List, Optional

async def create_hd_wallets(db: AsyncSession, count: int, start_index: int = None, tags: list = None):
    if start_index is None:
        # Find the maximum hd_index currently in DB
        result = await db.execute(select(func.max(Wallet.hd_index)).where(Wallet.is_hd == True))
        max_idx = result.scalar() or -1
        start_index = max_idx + 1

    wallet_data = generate_wallets(count, start_index)
    db_wallets = []
    for w in wallet_data:
        wallet = Wallet(
            address=w["address"],
            is_hd=True,
            hd_index=w["hd_index"],
            tags=tags or [],
            status="active",
            persona={}
        )
        db.add(wallet)
        await db.flush()
        db.add(WalletSettings(wallet_id=wallet.id))
        db_wallets.append(wallet)
    await db.commit()
    for w in db_wallets:
        await db.refresh(w)
    return db_wallets

# Keep the rest of the file unchanged
def normalize_private_key(raw: str) -> str:
    """Accept '0x'-prefixed or bare hex, tolerate surrounding whitespace, and return the
    64-char lowercase hex string. Raises ValueError with a user-readable message otherwise
    (never echoes the key itself)."""
    key = (raw or "").strip()
    if key[:2] in ("0x", "0X"):
        key = key[2:]
    if len(key) != 64:
        raise ValueError("Private key must be 64 hex characters (a leading 0x is fine)")
    try:
        int(key, 16)
    except ValueError:
        raise ValueError("Private key must contain only hex characters (0-9, a-f)")
    return key.lower()


async def import_private_key(db: AsyncSession, private_key: str, master_password: str, name: str = None, tags: list = None):
    from eth_keys import keys
    private_key = normalize_private_key(private_key)
    eth_key = keys.PrivateKey(bytes.fromhex(private_key))
    address = eth_key.public_key.to_checksum_address()
    encrypted = encrypt_private_key(private_key, master_password)
    wallet = Wallet(
        address=address,
        is_hd=False,
        encrypted_private_key=encrypted,
        name=name,
        tags=tags or [],
        status="active",
        persona={}
    )
    db.add(wallet)
    await db.flush()
    db.add(WalletSettings(wallet_id=wallet.id))
    await db.commit()
    await db.refresh(wallet)
    return wallet

async def list_wallets(db: AsyncSession, status_filter: Optional[str] = None, tag: Optional[str] = None) -> List[Wallet]:
    stmt = select(Wallet)
    if status_filter:
        stmt = stmt.where(Wallet.status == status_filter)
    if tag:
        stmt = stmt.where(Wallet.tags.contains(tag))
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_wallet(db: AsyncSession, wallet_id: int) -> Optional[Wallet]:
    return await db.get(Wallet, wallet_id)

async def update_wallet_status(db: AsyncSession, wallet_id: int, status: str):
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        return None
    wallet.status = status
    await db.commit()
    return wallet

async def archive_wallet(db: AsyncSession, wallet_id: int):
    return await update_wallet_status(db, wallet_id, "archived")
async def pause_wallet(db: AsyncSession, wallet_id: int):
    return await update_wallet_status(db, wallet_id, "paused")
async def resume_wallet(db: AsyncSession, wallet_id: int):
    return await update_wallet_status(db, wallet_id, "active")
async def blacklist_wallet(db: AsyncSession, wallet_id: int):
    return await update_wallet_status(db, wallet_id, "blacklisted")

async def set_gas_wallet_flag(db: AsyncSession, wallet_id: int, is_gas: bool):
    wallet = await db.get(Wallet, wallet_id)
    if wallet:
        wallet.is_gas_wallet = is_gas
        await db.commit()

async def get_wallet_settings(db: AsyncSession, wallet_id: int) -> Optional[WalletSettings]:
    result = await db.execute(select(WalletSettings).where(WalletSettings.wallet_id == wallet_id))
    return result.scalar_one_or_none()

async def update_wallet_settings(db: AsyncSession, wallet_id: int, **kwargs):
    settings = await get_wallet_settings(db, wallet_id)
    if not settings:
        settings = WalletSettings(wallet_id=wallet_id)
        db.add(settings)
    for key, value in kwargs.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    await db.commit()
    return settings
