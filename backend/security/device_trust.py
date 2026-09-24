from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from backend.config import SECRET_KEY, ALGORITHM, DEVICE_TRUST_EXPIRE_DAYS

DEVICE_TRUST_COOKIE_NAME = "device_trust"


def create_device_trust_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=DEVICE_TRUST_EXPIRE_DAYS)
    payload = {"sub": username, "type": "device_trust", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_device_trust_token(token: str, expected_username: str) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return False
    return payload.get("type") == "device_trust" and payload.get("sub") == expected_username
