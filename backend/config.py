import json
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY: str = os.getenv("SECRET_KEY", "please-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./airdrop.db")

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "4096"))

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = json.loads(os.getenv("TELEGRAM_ALLOWED_USER_IDS", "[]"))

# IP whitelist parsing
raw_ips = os.getenv("ALLOWED_IPS", "127.0.0.1,::1")
ALLOWED_IPS: List[str] = [ip.strip() for ip in raw_ips.split(",") if ip.strip()]

LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

MAX_WORKER_SLOTS: int = int(os.getenv("MAX_WORKER_SLOTS", "4"))
MEMORY_ALERT_THRESHOLD_PCT: float = float(os.getenv("MEMORY_ALERT_THRESHOLD_PCT", "82"))

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
DRY_RUN_MODE: bool = os.getenv("DRY_RUN_MODE", "false").lower() == "true"

MASTER_PASSWORD: str = os.getenv("MASTER_PASSWORD", "")

SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8002"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

DEVICE_TRUST_EXPIRE_DAYS: int = int(os.getenv("DEVICE_TRUST_EXPIRE_DAYS", "30"))
