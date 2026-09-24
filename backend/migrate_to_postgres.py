"""
Instructions to migrate from SQLite to PostgreSQL:
1. Install asyncpg: pip install asyncpg
2. Change DATABASE_URL in .env to: postgresql+asyncpg://user:pass@host/dbname
3. Run this script to create all tables:
   python -m backend.migrate_to_postgres
"""
import asyncio
from backend.database import engine, Base

async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    asyncio.run(migrate())
