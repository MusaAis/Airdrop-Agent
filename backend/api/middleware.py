from fastapi import FastAPI
from backend.security.ip_whitelist import IPWhitelistMiddleware
from backend.config import ALLOWED_IPS

def setup_middleware(app: FastAPI):
    app.add_middleware(IPWhitelistMiddleware, allowed_ips=ALLOWED_IPS)
