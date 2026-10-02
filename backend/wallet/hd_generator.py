from eth_account import Account
Account.enable_unaudited_hdwallet_features()
import logging
from typing import List, Optional
from eth_account import Account

logger = logging.getLogger("airdrop.hd")

_master_mnemonic: Optional[str] = None

def set_master_seed(mnemonic: str):
    global _master_mnemonic
    _master_mnemonic = mnemonic

def get_master_seed() -> Optional[str]:
    return _master_mnemonic

def derive_hd_wallet(index: int, mnemonic: Optional[str] = None) -> dict:
    """Derive Ethereum wallet at HD path m/44'/60'/0'/0/{index} using eth-account."""
    phrase = mnemonic or _master_mnemonic
    if not phrase:
        raise ValueError("No master seed set")

    # Derive the account at m/44'/60'/0'/0/index.
    # (The old code also built an unused Mnemonic/seed here; `HDWalletMnemonic("english")`
    # raises on eth-account >= 0.13, which would have broken every derivation after a
    # dependency upgrade. Account.from_mnemonic does all the work.)
    path = f"m/44'/60'/0'/0/{index}"
    account = Account.from_mnemonic(phrase, account_path=path)
    return {
        "address": account.address,
        "private_key": account.key.hex(),
        "hd_index": index,
        "path": path
    }

def generate_wallets(count: int, start_index: int = 0) -> List[dict]:
    """Generate multiple HD wallets."""
    wallets = []
    for i in range(count):
        wallets.append(derive_hd_wallet(start_index + i))
    return wallets

# --- encrypted storage helpers (unchanged) ---
from backend.config import MASTER_PASSWORD

from backend.wallet.crypto import encrypt_private_key, decrypt_private_key

def encrypt_seed(seed_phrase: str, password: str) -> str:
    return encrypt_private_key(seed_phrase, password)

def decrypt_seed(encrypted_seed: str, password: str) -> str:
    return decrypt_private_key(encrypted_seed, password)
