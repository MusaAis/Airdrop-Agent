import ipaddress
from typing import List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

SKIP_PATHS = ["/agent/health", "/auth/login", "/auth/refresh", "/openapi.json", "/docs", "/redoc", "/ws/logs"]


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_ips: List[str]):
        super().__init__(app)
        self.allowed_ips = allowed_ips
        self.networks = []
        for ip in allowed_ips:
            try:
                self.networks.append(ipaddress.ip_network(ip, strict=False))
            except ValueError:
                self.networks.append(ipaddress.ip_network(ip + "/32", strict=False))

    async def __call__(self, scope, receive, send):
        # BaseHTTPMiddleware.dispatch can't handle websocket scope (raises
        # NotImplementedError). Bypass it entirely for non-http scopes.
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        return await super().__call__(scope, receive, send)

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in SKIP_PATHS:
            return await call_next(request)

        client_ip = (
            request.headers.get("cf-connecting-ip")
            or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.client.host
        )

        try:
            ip_obj = ipaddress.ip_address(client_ip)
        except ValueError:
            return JSONResponse(status_code=403, content={"detail": "IP not allowed"})

        if not any(ip_obj in net for net in self.networks):
            return JSONResponse(status_code=403, content={"detail": "IP not allowed"})
        return await call_next(request)
