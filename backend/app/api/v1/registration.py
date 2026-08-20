from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.registration_service import refresh_window

router = APIRouter(prefix="/contests/ai-weekly", tags=["contests"])


@router.get("/registration-status")
async def ai_weekly_registration_status(db: AsyncSession = Depends(get_db)):
    """Whether registration for the AI Weekly Exam is currently open.
    Unrelated to account signup, which is open every day."""
    window = await refresh_window(db)
    await db.commit()
    return {
        "is_open": window.is_open,
        "next_open_at": window.next_open_at.astimezone(UTC).isoformat() if window.next_open_at else None,
        "message": (
            "AI Weekly Exam registration is open today."
            if window.is_open
            else "AI Weekly Exam registration is closed. It opens every Thursday (IST)."
        ),
    }
