from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.registration_service import refresh_window

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/registration-status")
async def registration_status(db: AsyncSession = Depends(get_db)):
    window = await refresh_window(db)
    await db.commit()
    return {
        "is_open": window.is_open,
        "next_open_at": window.next_open_at.astimezone(timezone.utc).isoformat() if window.next_open_at else None,
        "message": (
            "Registration is open today."
            if window.is_open
            else "Registration is closed. It opens every Thursday (IST)."
        ),
    }
