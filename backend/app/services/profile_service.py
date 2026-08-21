"""Unique @handle claiming — shared by registration (every account gets one
up front) and the later profile-edit path, so both go through the same
validation and the same race-safe claim logic rather than drifting apart."""
from __future__ import annotations

import re
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationAppError
from app.models.user import Profile

HANDLE_PATTERN = re.compile(r"^[a-z0-9_]{3,30}$")


def normalize_handle(raw: str) -> str:
    handle = raw.strip().lower()
    if not HANDLE_PATTERN.match(handle):
        raise ValidationAppError("Usernames must be 3-30 characters: lowercase letters, numbers, and underscores only.")
    return handle


def fallback_handle(user_id: uuid.UUID) -> str:
    """Deterministic from the user's own id, so it's unique by construction
    with no lookup/retry needed — used only to backfill accounts that
    predate the required-at-signup username (see the profiles.public_handle
    backfill migration and _get_or_create_profile in users.py)."""
    return f"user_{uuid.UUID(str(user_id)).hex[:12]}"


async def create_profile_with_handle(db: AsyncSession, user_id: uuid.UUID, raw_handle: str) -> Profile:
    """Registration path: the account's Profile row and its @handle are
    created together, atomically. A SAVEPOINT + IntegrityError catch turns a
    genuine claim-race against another signup into a clean 409 instead of an
    unhandled 500 — the caller (POST /auth/register) hasn't committed
    anything yet, so on conflict the whole registration rolls back rather
    than leaving a user account with no handle."""
    handle = normalize_handle(raw_handle)
    profile = Profile(user_id=user_id, public_handle=handle)
    try:
        async with db.begin_nested():
            db.add(profile)
            await db.flush()
    except IntegrityError:
        raise ConflictError("That username is already taken.") from None
    return profile


async def set_profile_handle(db: AsyncSession, profile: Profile, raw_handle: str) -> None:
    """Profile-edit path (PATCH /users/me/profile): same race-safety as
    create_profile_with_handle, for an already-existing row changing its
    handle."""
    handle = normalize_handle(raw_handle)
    if handle == profile.public_handle:
        return
    profile.public_handle = handle
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("That username is already taken.") from None
