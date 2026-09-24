from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import User
from backend.security.auth import verify_password, create_access_token, create_refresh_token, decode_token, get_password_hash
from backend.security.brute_force import BruteForceProtector
from backend.security.totp import generate_totp_secret, get_totp_uri, generate_qr_code_base64, verify_totp_code
from backend.security.device_trust import create_device_trust_token, verify_device_trust_token, DEVICE_TRUST_COOKIE_NAME
from backend.config import LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_MINUTES, DEVICE_TRUST_EXPIRE_DAYS
from pydantic import BaseModel

router = APIRouter(tags=["auth"])
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
    if not user or not verify_password(data.password, user.hashed_password):
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


@router.post("/refresh")
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    payload = decode_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    new_access = create_access_token(data={"sub": payload.get("sub")})
    return {"access_token": new_access, "token_type": "bearer"}


from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── TOTP enrollment (call these once, while logged in, to turn on 2FA) ──

class TOTPVerifyRequest(BaseModel):
    totp_code: str


@router.post("/totp/setup")
async def totp_setup(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    secret = generate_totp_secret()
    user.totp_secret = secret
    user.totp_enabled = False  # stays off until verified below
    await db.commit()
    uri = get_totp_uri(secret, user.username)
    qr_b64 = generate_qr_code_base64(uri)
    return {"secret": secret, "qr_code_base64": qr_b64}


@router.post("/totp/verify-setup")
async def totp_verify_setup(
    data: TOTPVerifyRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Run /totp/setup first")
    if not verify_totp_code(user.totp_secret, data.totp_code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    user.totp_enabled = True
    await db.commit()
    return {"totp_enabled": True}


@router.post("/totp/disable")
async def totp_disable(
    data: TOTPVerifyRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if not user.totp_enabled or not verify_totp_code(user.totp_secret, data.totp_code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()
    return {"totp_enabled": False}
