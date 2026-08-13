from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.analytics_service import track_event

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Event types the frontend is allowed to self-report — deliberately a strict
# allowlist so clients can't inject arbitrary event_type strings into the
# Power BI-facing dataset.
_ALLOWED_CLIENT_EVENTS = {"page_view", "ai_interaction", "chat_activity", "search"}


class ClientEvent(BaseModel):
    event_type: str
    metadata: dict = {}
    session_id: str | None = None


@router.post("/events", status_code=202)
async def track_client_event(payload: ClientEvent, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if payload.event_type not in _ALLOWED_CLIENT_EVENTS:
        return {"accepted": False}
    await track_event(db, event_type=payload.event_type, user_id=user.id, session_id=payload.session_id, metadata=payload.metadata)
    await db.commit()
    return {"accepted": True}
