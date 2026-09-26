from fastapi import APIRouter, Depends, HTTPException, Query
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.reports.eligibility import get_eligibility_report
from backend.reports.gas_spend import get_gas_spend_report
from backend.reports.daily_progress import get_daily_progress_report
from backend.reports.gas import get_gas_usage_report
from backend.reports.sybil import get_sybil_report
from backend.reports.activity import get_activity_log
from backend.reports.performance import get_avg_confirmation_time, get_worker_utilization, get_rpc_latency_percentiles
from backend.reports.server import get_server_status
from backend.reports.export import export_csv
from fastapi.responses import PlainTextResponse
from backend.reports.performance import get_avg_confirmation_time, get_worker_utilization, get_rpc_latency_percentiles

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/performance/avg-confirmation/{chain_id}")
async def avg_confirmation(chain_id: int, _user: dict = Depends(verify_token), hours: int = 24):
    return await get_avg_confirmation_time(chain_id, hours)

@router.get("/performance/worker-utilization")
async def worker_utilization(_user: dict = Depends(verify_token)):
    return await get_worker_utilization()

@router.get("/performance/rpc-latency/{chain_id}")
async def rpc_latency(chain_id: int, _user: dict = Depends(verify_token)):
    return await get_rpc_latency_percentiles(chain_id)

@router.get("/eligibility")
async def eligibility_report(_user: dict = Depends(verify_token), project_id: int = None, db: AsyncSession = Depends(get_db)):
    return await get_eligibility_report(db, project_id)

@router.get("/gas-spend")
async def gas_spend_report(_user: dict = Depends(verify_token), project_id: int = None, db: AsyncSession = Depends(get_db)):
    return await get_gas_spend_report(db, project_id)

@router.get("/daily-progress")
async def daily_progress_report(_user: dict = Depends(verify_token), project_id: int = None, db: AsyncSession = Depends(get_db)):
    return await get_daily_progress_report(db, project_id)

@router.get("/gas")
async def gas_report(_user: dict = Depends(verify_token), chain_id: int = None, db: AsyncSession = Depends(get_db)):
    return await get_gas_usage_report(db, chain_id)

@router.get("/sybil")
async def sybil_report(_user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    return await get_sybil_report(db)

@router.get("/activity")
async def activity_log(_user: dict = Depends(verify_token), hours: int = 24, wallet_id: int = None, db: AsyncSession = Depends(get_db)):
    return await get_activity_log(db, hours, wallet_id)

@router.get("/server")
async def server_status(_user: dict = Depends(verify_token)):
    return get_server_status()

@router.get("/export/{table}")
async def export_table(table: str, _user: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    if table not in ("transactions", "wallets"):
        raise HTTPException(400, "Table not supported")
    csv_data = await export_csv(db, table)
    return PlainTextResponse(content=csv_data, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={table}.csv"})
@router.get("/performance/avg-confirmation/{chain_id}")
async def avg_confirmation(chain_id: int, _user: dict = Depends(verify_token), hours: int = 24):
    return await get_avg_confirmation_time(chain_id, hours)

@router.get("/performance/worker-utilization")
async def worker_utilization(_user: dict = Depends(verify_token)):
    return await get_worker_utilization()

@router.get("/performance/rpc-latency/{chain_id}")
async def rpc_latency(chain_id: int, _user: dict = Depends(verify_token)):
    return await get_rpc_latency_percentiles(chain_id)


