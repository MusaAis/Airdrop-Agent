import time
from typing import Dict, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import User
from backend.security.auth import (
    verify_password, create_access_token, create_refresh_token, decode_token,
    get_password_hash, TOKEN_TYPE_ACCESS, TOKEN_TYPE_REFRESH,
)
from backend.security.brute_force import BruteForceProtector
from backend.security.totp import generate_totp_secret, get_totp_uri, generate_qr_code_base64, verify_totp_code
from backend.security.device_trust import create_device_trust_token, verify_device_trust_token, DEVICE_TRUST_COOKIE_NAME
from backend.config import LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_MINUTES, DEVICE_TRUST_EXPIRE_DAYS
from pydantic import BaseModel

router = APIRouter(tags=["auth"])
_dummy_hash_cache: Optional[str] = None


def _dummy_hash() -> str:
    global _dummy_hash_cache
    if _dummy_hash_cache is None:
        _dummy_hash_cache = get_password_hash("not-a-real-password")
    return _dummy_hash_cache


brute_force = BruteForceProtector(LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_MINUTES)


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None
    remember_device: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, response: Response, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host
    if brute_force.is_blocked(client_ip) or await brute_force.check_db_blocked(client_ip, db):
        raise HTTPException(status_code=429, detail="Too many attempts, try later")

    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    # Always run one bcrypt verification so response time does not reveal whether
    # the username exists.
    password_ok = verify_password(data.password, user.hashed_password if user else _dummy_hash())
    if not user or not password_ok:
        await brute_force.record_failure_db(client_ip, db)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    device_cookie = request.cookies.get(DEVICE_TRUST_COOKIE_NAME)
    device_trusted = bool(device_cookie) and verify_device_trust_token(device_cookie, user.username)

    if user.totp_enabled and not device_trusted:
        if not data.totp_code:
            raise HTTPException(status_code=401, detail="totp_required")
        if not verify_totp_code(user.totp_secret, data.totp_code):
            await brute_force.record_failure_db(client_ip, db)
            raise HTTPException(status_code=401, detail="Invalid TOTP code")

    brute_force.reset(client_ip)
    await brute_force.record_success_db(client_ip, db)
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    if data.remember_device:
        response.set_cookie(
            key=DEVICE_TRUST_COOKIE_NAME,
            value=create_device_trust_token(user.username),
            max_age=DEVICE_TRUST_EXPIRE_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=True,
            samesite="none",
        )

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a REFRESH token (request body, never the URL) for a new access token.
    Access tokens and device-trust tokens are rejected, and the user must still exist."""
    payload = decode_token(data.refresh_token, TOKEN_TYPE_REFRESH)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.username == payload["sub"]))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"access_token": create_access_token(data={"sub": payload["sub"]}), "token_type": "bearer"}


from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    payload = decode_token(token, TOKEN_TYPE_ACCESS)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.username == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── TOTP enrollment (call these while logged in to turn on / replace 2FA) ──
#
# Replacing or disabling the second factor must need more than a bearer token, otherwise
# a stolen 30-minute access token could take over 2FA permanently:
#   * /totp/setup needs the account password, plus a current TOTP code when 2FA is on.
#   * The new secret is held in memory until /totp/verify-setup proves the authenticator
#     works. The existing secret stays active (and 2FA stays on) until then.
#   * All three endpoints share a small per-user failure limiter.

_PENDING_TTL_SECS = 600
_pending_totp: Dict[str, Tuple[str, float]] = {}      # username -> (secret, expires_at)

_SENSITIVE_MAX_FAILS = 5
_SENSITIVE_WINDOW_SECS = 15 * 60
_sensitive_fails: Dict[str, list] = {}                # username -> [timestamps]


def _sensitive_check(username: str) -> None:
    now = time.time()
    recent = [t for t in _sensitive_fails.get(username, []) if now - t < _SENSITIVE_WINDOW_SECS]
    _sensitive_fails[username] = recent
    if len(recent) >= _SENSITIVE_MAX_FAILS:
        raise HTTPException(status_code=429, detail="Too many failed attempts, try later")


def _sensitive_fail(username: str, detail: str, status_code: int = 401):
    _sensitive_fails.setdefault(username, []).append(time.time())
    raise HTTPException(status_code=status_code, detail=detail)


class TOTPSetupRequest(BaseModel):
    password: str
    totp_code: Optional[str] = None      # required when 2FA is already enabled


class TOTPVerifyRequest(BaseModel):
    totp_code: str


class TOTPDisableRequest(BaseModel):
    password: str
    totp_code: str


@router.post("/totp/setup")
async def totp_setup(
    data: TOTPSetupRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _sensitive_check(user.username)
    if not verify_password(data.password, user.hashed_password):
        _sensitive_fail(user.username, "Invalid password")
    if user.totp_enabled:
        if not data.totp_code or not verify_totp_code(user.totp_secret, data.totp_code):
            _sensitive_fail(user.username, "Current TOTP code required to replace 2FA")
    secret = generate_totp_secret()
    _pending_totp[user.username] = (secret, time.time() + _PENDING_TTL_SECS)
    uri = get_totp_uri(secret, user.username)
    qr_b64 = generate_qr_code_base64(uri)
    return {"secret": secret, "qr_code_base64": qr_b64}


@router.post("/totp/verify-setup")
async def totp_verify_setup(
    data: TOTPVerifyRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _sensitive_check(user.username)
    pending = _pending_totp.get(user.username)
    if not pending or pending[1] < time.time():
        _pending_totp.pop(user.username, None)
        raise HTTPException(status_code=400, detail="Run /auth/totp/setup first")
    if not verify_totp_code(pending[0], data.totp_code):
        _sensitive_fail(user.username, "Invalid TOTP code")
    user.totp_secret = pending[0]
    user.totp_enabled = True
    await db.commit()
    _pending_totp.pop(user.username, None)
    return {"totp_enabled": True}


@router.post("/totp/disable")
async def totp_disable(
    data: TOTPDisableRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _sensitive_check(user.username)
    if not verify_password(data.password, user.hashed_password):
        _sensitive_fail(user.username, "Invalid password")
    if not user.totp_enabled or not verify_totp_code(user.totp_secret, data.totp_code):
        _sensitive_fail(user.username, "Invalid TOTP code")
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()
    return {"totp_enabled": False}
