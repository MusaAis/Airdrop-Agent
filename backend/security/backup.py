import os
import asyncio
import base64
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from backend.config import MASTER_PASSWORD, OCI_BUCKET_NAME, OCI_NAMESPACE, OCI_CONFIG_FILE
import logging

logger = logging.getLogger("airdrop.backup")

def derive_key(master_password: str) -> bytes:
    # Derive a 32-byte key from master password using simple deterministic method (PBKDF2 later)
    import hashlib
    return base64.urlsafe_b64encode(hashlib.sha256(master_password.encode()).digest())

async def encrypted_backup(db_path: str):
    try:
        key = derive_key(MASTER_PASSWORD)
        fernet = Fernet(key)
        with open(db_path, "rb") as f:
            db_data = f.read()
        encrypted = fernet.encrypt(db_data)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"airdrop_{timestamp}.db.enc"
        # Upload to Oracle Object Storage using OCI CLI (subprocess)
        # For simplicity, we'll just save locally; replace with oci command
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        local_path = os.path.join(backup_dir, filename)
        with open(local_path, "wb") as f:
            f.write(encrypted)
        logger.info(f"Encrypted backup saved locally: {local_path}")
        # Optionally upload via OCI CLI
        # subprocess.run(["oci", "os", "object", "put", "--bucket-name", OCI_BUCKET_NAME, ...])
    except Exception as e:
        logger.error(f"Backup failed: {e}")
