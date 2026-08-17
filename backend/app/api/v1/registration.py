from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth
from app.core.exceptions import ValidationAppError
from app.database import get_db
from app.schemas.auth import RegisterRequest, UserOut
from app.services.registration_service import refresh_window, registration_is_open

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not registration_is_open():
        raise ValidationAppError(
            "Registration is closed every Thursday (IST). Please try again on another day.",
            code="registration_closed",
        )
    return await auth.register(payload, request, db)


@router.get("/registration-status")
async def registration_status(db: AsyncSession = Depends(get_db)):
    window = await refresh_window(db)
    await db.commit()
    return {
        "is_open": window.is_open,
        "next_open_at": window.next_open_at.astimezone(timezone.utc).isoformat() if window.next_open_at else None,
        "message": (
            "Registration is closed every Thursday (IST)."
            if not window.is_open
            else "Registration is open today."
        ),
    }
