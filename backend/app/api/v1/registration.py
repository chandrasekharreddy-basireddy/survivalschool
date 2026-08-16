from __future__ import annotations

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
        "next_open_at": window.next_open_at.isoformat() if window.next_open_at else None,
        "override_until": window.override_until.isoformat() if window.override_until else None,
        "message": "Registration is open today." if window.is_open else "Registration opens every Thursday (IST).",
    }
