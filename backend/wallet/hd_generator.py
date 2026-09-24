from eth_account import Account
Account.enable_unaudited_hdwallet_features()
import logging
from typing import List, Optional
from mnemonic import Mnemonic
from eth_account.hdaccount import Mnemonic as HDWalletMnemonic
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

    # Generate seed from mnemonic
    mnemo = Mnemonic("english")
    seed = mnemo.to_seed(phrase)

    # Use eth-account HD wallet
    hd_mnemonic = HDWalletMnemonic("english")
    master_key = hd_mnemonic.to_seed(phrase)   # same as seed
    # Derive the account at m/44'/60'/0'/0/index
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
