from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling import RegistrationWindow

IST = ZoneInfo("Asia/Kolkata")
THURSDAY = 3


def next_registration_open_ist(now: datetime | None = None) -> datetime:
    current = (now or datetime.now(timezone.utc)).astimezone(IST)
    target = current
    if current.weekday() == THURSDAY or current.time() >= time(23, 59, 59):
        target = current + timedelta(days=1)
    while target.weekday() == THURSDAY:
        target += timedelta(days=1)
    return datetime.combine(target.date(), time(0, 0), tzinfo=IST)


def registration_is_open(now: datetime | None = None, override_until: datetime | None = None) -> bool:
    current = (now or datetime.now(timezone.utc)).astimezone(IST)
    return current.weekday() != THURSDAY


async def get_or_create_window(db: AsyncSession) -> RegistrationWindow:
    result = await db.execute(select(RegistrationWindow).order_by(RegistrationWindow.created_at).limit(1))
    window = result.scalar_one_or_none()
    if window is None:
        window = RegistrationWindow(next_open_at=next_registration_open_ist())
        db.add(window)
        await db.flush()
    return window


async def refresh_window(db: AsyncSession) -> RegistrationWindow:
    window = await get_or_create_window(db)
    now = datetime.now(timezone.utc)
    window.next_open_at = next_registration_open_ist(now)
    window.is_open = registration_is_open(now, window.override_until)
    return window
