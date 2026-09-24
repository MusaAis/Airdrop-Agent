from fastapi import APIRouter, Depends, HTTPException
from backend.security.auth import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from typing import List, Dict, Any
import httpx
import json

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# In-memory registry (for production, store in DB)
webhook_registry: List[Dict[str, Any]] = []

@router.post("/register")
async def register_webhook(url: str, events: List[str], _user: dict = Depends(verify_token)):
    webhook_registry.append({"url": url, "events": events})
    return {"message": "Webhook registered", "id": len(webhook_registry)-1}

@router.post("/unregister/{webhook_id}")
async def unregister_webhook(webhook_id: int, _user: dict = Depends(verify_token)):
    if webhook_id < len(webhook_registry):
        webhook_registry.pop(webhook_id)
        return {"message": "Removed"}
    raise HTTPException(404, "Webhook not found")

async def dispatch_event(event_type: str, data: dict, _user: dict = Depends(verify_token)):
    for hook in webhook_registry:
        if event_type in hook["events"]:
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(hook["url"], json={"event": event_type, "data": data})
                except Exception as e:
                    pass
