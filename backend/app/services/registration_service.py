from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling import RegistrationWindow

IST = ZoneInfo("Asia/Kolkata")


def next_thursday_ist(now: datetime | None = None) -> datetime:
    current = (now or datetime.now(UTC)).astimezone(IST)
    days_ahead = (3 - current.weekday()) % 7
    if days_ahead == 0 and current.time() >= time(23, 59, 59):
        days_ahead = 7
    target = current + timedelta(days=days_ahead)
    return datetime.combine(target.date(), time(0, 0), tzinfo=IST)


def registration_is_open(now: datetime | None = None, override_until: datetime | None = None) -> bool:
    current = (now or datetime.now(UTC)).astimezone(IST)
    return (override_until is not None and current < override_until.astimezone(IST)) or current.weekday() == 3


async def get_or_create_window(db: AsyncSession) -> RegistrationWindow:
    result = await db.execute(select(RegistrationWindow).order_by(RegistrationWindow.created_at).limit(1))
    window = result.scalar_one_or_none()
    if window is None:
        # Two concurrent first-hits (this is reachable from an unauthenticated
        # endpoint) can both find no row and both try to insert. The unique
        # constraint on `singleton` makes the loser fail rather than create a
        # duplicate; catch it inside a SAVEPOINT and re-read the winner's row.
        window = RegistrationWindow(next_open_at=next_thursday_ist())
        try:
            async with db.begin_nested():
                db.add(window)
                await db.flush()
        except IntegrityError:
            window = (await db.execute(
                select(RegistrationWindow).order_by(RegistrationWindow.created_at).limit(1)
            )).scalar_one()
    return window


async def refresh_window(db: AsyncSession) -> RegistrationWindow:
    """Recompute the singleton registration window's derived fields.

    Only assigns a field when its computed value actually differs from what's
    stored — this is reached from an unauthenticated, unrate-limited endpoint
    (GET /auth/registration-status) polled by every visitor on the register
    page, so an unconditional assignment here marks the row dirty on every
    call and forces an UPDATE + commit even when nothing changed — genuine
    write amplification with no bound on it. The two fields only actually
    change once a day (next_open_at rolling over) or at the moment the window
    flips open/closed, so this makes the overwhelming majority of calls a
    true no-op UPDATE-wise.
    """
    window = await get_or_create_window(db)
    now = datetime.now(UTC)
    next_open = next_thursday_ist(now)
    is_open = registration_is_open(now, window.override_until)
    if window.next_open_at != next_open:
        window.next_open_at = next_open
    if window.is_open != is_open:
        window.is_open = is_open
    return window
