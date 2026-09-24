from datetime import datetime, timedelta, timezone
from collections import defaultdict

class BruteForceProtector:
    def __init__(self, max_attempts: int, lockout_minutes: int):
        self.max_attempts = max_attempts
        self.lockout_minutes = lockout_minutes
        self.failures = defaultdict(list)

    def is_blocked(self, ip: str) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.lockout_minutes)
        self.failures[ip] = [t for t in self.failures[ip] if t > cutoff]
        return len(self.failures[ip]) >= self.max_attempts

    async def check_db_blocked(self, ip: str, db) -> bool:
        """Check DB-persisted failures — survives server restarts."""
        from sqlalchemy import select, func
        from backend.models import LoginAttempt
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.lockout_minutes)
        result = await db.execute(
            select(func.count()).select_from(LoginAttempt).where(
                LoginAttempt.ip_address == ip,
                LoginAttempt.success == False,
                LoginAttempt.created_at >= cutoff,
            )
        )
        return (result.scalar() or 0) >= self.max_attempts

    def record_failure(self, ip: str):
        self.failures[ip].append(datetime.now(timezone.utc))

    async def record_failure_db(self, ip: str, db):
        from backend.models import LoginAttempt
        self.record_failure(ip)
        db.add(LoginAttempt(ip_address=ip, success=False, created_at=datetime.now(timezone.utc)))
        await db.commit()

    async def record_success_db(self, ip: str, db):
        from backend.models import LoginAttempt
        db.add(LoginAttempt(ip_address=ip, success=True, created_at=datetime.now(timezone.utc)))
        await db.commit()

    def reset(self, ip: str):
        self.failures[ip] = []
