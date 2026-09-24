import os
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# Blob layout: salt[16] | iv[16] | ciphertext[N]
# A fresh random 16-byte salt is generated per encryption so no two wallets
# share a KDF salt even under the same master password.
_SALT_LEN = 16
_IV_LEN   = 16
_PBKDF2_ITERS = 600_000

def _derive_key(master_password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt,
        iterations=_PBKDF2_ITERS, backend=default_backend(),
    )
    return kdf.derive(master_password.encode())

def encrypt_private_key(private_key_hex: str, master_password: str) -> str:
    salt = os.urandom(_SALT_LEN)
    iv   = os.urandom(_IV_LEN)
    key  = _derive_key(master_password, salt)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    enc = cipher.encryptor()
    plaintext = private_key_hex.encode()
    pad = 16 - (len(plaintext) % 16)
    ct = enc.update(plaintext + bytes([pad] * pad)) + enc.finalize()
    return base64.b64encode(salt + iv + ct).decode()

def decrypt_private_key(encrypted_b64: str, master_password: str) -> str:
    data = base64.b64decode(encrypted_b64)
    salt = data[:_SALT_LEN]
    iv   = data[_SALT_LEN:_SALT_LEN + _IV_LEN]
    ct   = data[_SALT_LEN + _IV_LEN:]
    key  = _derive_key(master_password, salt)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    dec = cipher.decryptor()
    padded = dec.update(ct) + dec.finalize()
    return padded[:-padded[-1]].decode()
