from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# Every JWT this app signs carries a "type" claim. All of them share one key, so
# without the claim a refresh token (7 days) or the device-trust cookie (30 days)
# would also be accepted as a Bearer access token, and any access token could be
# "refreshed" forever. Each consumer now states which type it accepts.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def _encode(data: dict, token_type: str, expires: timedelta) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + expires, "type": token_type})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    return _encode(data, TOKEN_TYPE_ACCESS,
                   expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(data: dict) -> str:
    return _encode(data, TOKEN_TYPE_REFRESH, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: str) -> Optional[dict]:
    """Return the payload only if the signature, expiry AND token type all match.
    expected_type is required on purpose: there is no way to call this and skip the check."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != expected_type or not payload.get("sub"):
        return None
    return payload


def verify_token_str(token: str) -> dict:
    """
    Verify a raw ACCESS token string (used by WebSocket — no HTTP header wrapper).
    Raises HTTPException 401 if invalid, expired or not an access token.
    """
    payload = decode_token(token, TOKEN_TYPE_ACCESS)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI dependency for Bearer token auth on HTTP routes.
    """
    return verify_token_str(credentials.credentials)
