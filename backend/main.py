import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import auth, agent, ws, chains, wallets, faucets, projects, ai, reports, webhooks, autonomy, ops, stats, proxies
from backend.database import init_db, async_session
from backend.config import SERVER_HOST, SERVER_PORT, LOG_LEVEL, MASTER_PASSWORD
from sqlalchemy import select
from backend.models import User
from backend.security.auth import get_password_hash
import backend.core.autonomy_models  # noqa: F401  (registers ai_actions tables before init_db)
import uvicorn

app = FastAPI(title="Airdrop Agent", version="0.1.0")

# from backend.api.middleware import setup_middleware
# setup_middleware(app)

# CORS must be added before any other middleware/routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://airdrop-agent-wine.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(agent.router)
app.include_router(ws.router)
app.include_router(chains.router)
app.include_router(wallets.router)
app.include_router(faucets.router)
app.include_router(projects.router)
app.include_router(ai.router)
app.include_router(reports.router)
app.include_router(webhooks.router)
app.include_router(autonomy.router)
app.include_router(ops.router)       # Phase 7: control-panel endpoints
app.include_router(stats.router)     # Phase 7: stats overview
app.include_router(proxies.router)   # Phase 7: proxy management

@app.on_event("startup")
async def startup():
    await init_db()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one_or_none()
        if not user:
            session.add(User(username="admin", hashed_password=get_password_hash(MASTER_PASSWORD)))
            await session.commit()

    # Phase 6: restore the persisted AI-autonomy freeze flag BEFORE the
    # scheduler starts, so a restart can never silently re-enable autonomy.
    from backend.core.autonomy import load_autonomy_state
    await load_autonomy_state()

    # Start APScheduler background jobs (faucet check, sybil re-score, log
    # archival, daily summary, gas sampling, contract check, failure analysis,
    # AI autonomy)
    from backend.core.scheduler import start_scheduler
    start_scheduler()

    # Start the main agent loop as a background task
    from backend.agent import agent_loop
    asyncio.create_task(agent_loop())

    # Start Telegram bot if configured
    from backend.config import TELEGRAM_BOT_TOKEN
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != "123456:ABC-DEF1234gh":
        from backend.telegram.bot import start_bot
        asyncio.create_task(start_bot())

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host=SERVER_HOST, port=SERVER_PORT, log_level=LOG_LEVEL.lower())
