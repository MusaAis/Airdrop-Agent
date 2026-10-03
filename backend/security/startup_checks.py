"""
Refuse to start with unsafe secrets (review item C8).

MASTER_PASSWORD is the admin login password AND the key that encrypts imported private
keys and the stored master seed. An empty value used to create an admin account with an
empty password, and SECRET_KEY defaulted to a publicly known string, which lets anyone
forge a login token.

Hard errors stop the process. Soft warnings are only logged: a short-but-real
MASTER_PASSWORD may already be protecting encrypted keys, and changing it would make
them undecryptable, so we never force a change beyond the clearly unsafe cases.
"""
import logging
from typing import List, Tuple

logger = logging.getLogger("airdrop.security")

# Values shipped in .env.example / config defaults: copied-and-forgotten placeholders.
PLACEHOLDER_SECRETS = {
    "please-change-me-in-production",
    "change-me-to-a-random-64-char-string",
    "your-strong-master-password-here",
    "changeme", "change-me", "password", "admin", "secret",
}
MIN_SECRET_KEY_LEN = 32
MIN_MASTER_PASSWORD_LEN = 8        # hard floor
RECOMMENDED_MASTER_PASSWORD_LEN = 12
BCRYPT_MAX_BYTES = 72              # bcrypt silently ignores (or rejects) bytes beyond this


def check_secrets(secret_key: str, master_password: str) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings). Pure function so it can be unit-tested."""
    errors: List[str] = []
    warnings: List[str] = []

    sk = (secret_key or "").strip()
    if not sk or sk.lower() in PLACEHOLDER_SECRETS:
        errors.append("SECRET_KEY is empty or a known placeholder. Generate one: "
                      "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    elif len(sk) < MIN_SECRET_KEY_LEN:
        errors.append(f"SECRET_KEY must be at least {MIN_SECRET_KEY_LEN} characters (got {len(sk)}). "
                      "Changing it only signs everyone out, so it is safe to rotate.")

    mp = master_password or ""
    if not mp.strip():
        errors.append("MASTER_PASSWORD is empty. It is the admin password and the key-encryption "
                      "password for wallets and the master seed.")
    elif mp.strip().lower() in PLACEHOLDER_SECRETS:
        errors.append("MASTER_PASSWORD is a known placeholder from .env.example.")
    elif len(mp) < MIN_MASTER_PASSWORD_LEN:
        errors.append(f"MASTER_PASSWORD must be at least {MIN_MASTER_PASSWORD_LEN} characters.")
    else:
        if len(mp) < RECOMMENDED_MASTER_PASSWORD_LEN:
            warnings.append(f"MASTER_PASSWORD is shorter than {RECOMMENDED_MASTER_PASSWORD_LEN} characters. "
                            "Changing it requires re-encrypting imported keys and the stored seed.")
        if len(mp.encode("utf-8")) > BCRYPT_MAX_BYTES:
            warnings.append(f"MASTER_PASSWORD is longer than {BCRYPT_MAX_BYTES} bytes; the admin login "
                            "hash only uses the first 72 bytes (key encryption uses all of it).")
    return errors, warnings


def enforce_startup_secrets(secret_key: str, master_password: str, allow_insecure: bool = False) -> None:
    """Call once at startup. Raises SystemExit on unsafe configuration."""
    errors, warnings = check_secrets(secret_key, master_password)
    for w in warnings:
        logger.warning("SECURITY: %s", w)
    if not errors:
        return
    for e in errors:
        logger.error("SECURITY: %s", e)
    if allow_insecure:
        logger.critical("ALLOW_INSECURE_SECRETS=true: starting with unsafe secrets. "
                        "Never use this on a reachable server.")
        return
    raise SystemExit(
        "Refusing to start with unsafe secrets:\n  - " + "\n  - ".join(errors) +
        "\nFix them in .env (see .env.example). For local throwaway development only you can set "
        "ALLOW_INSECURE_SECRETS=true."
    )
