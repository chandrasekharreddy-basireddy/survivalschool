from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db_utils import escape_like
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.social_graph import FollowRequest
from app.models.user import Profile, User
from app.schemas.auth import MessageResponse
from app.schemas.social_graph import (
    ConnectionOut,
    FollowRequestCreate,
    FollowRequestOut,
    PersonSearchResultOut,
)
from app.services.rate_limit_service import enforce_rate_limit
from app.services.social_graph_service import has_accepted_connection

router = APIRouter(prefix="/follows", tags=["follows"])
settings = get_settings()


async def _handle_for(db: AsyncSession, user_id: uuid.UUID) -> str | None:
    profile = (await db.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one_or_none()
    return profile.public_handle if profile else None


async def _to_out(db: AsyncSession, req: FollowRequest) -> FollowRequestOut:
    return (await _to_out_many(db, [req]))[0]


async def _to_out_many(db: AsyncSession, reqs: list[FollowRequest]) -> list[FollowRequestOut]:
    """Same shape as _to_out, batched — _to_out itself does 4 queries per
    row (2x db.get(User) + 2x _handle_for's Profile lookup), which is fine
    for the single-row accept/decline responses but was also being used to
    build list_incoming_requests/list_outgoing_requests one row at a time,
    an N+1 for what should be 2 queries total regardless of list length."""
    if not reqs:
        return []
    user_ids = {r.requester_id for r in reqs} | {r.target_id for r in reqs}
    users = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    }
    profiles = {
        p.user_id: p for p in (await db.execute(select(Profile).where(Profile.user_id.in_(user_ids)))).scalars().all()
    }

    def _name(uid: uuid.UUID) -> str:
        u = users.get(uid)
        return u.full_name if u else "Unknown"

    def _handle(uid: uuid.UUID) -> str | None:
        p = profiles.get(uid)
        return p.public_handle if p else None

    return [
        FollowRequestOut(
            id=r.id, requester_id=r.requester_id, requester_name=_name(r.requester_id),
            requester_handle=_handle(r.requester_id),
            target_id=r.target_id, target_name=_name(r.target_id),
            target_handle=_handle(r.target_id),
            status=r.status, created_at=r.created_at, responded_at=r.responded_at,
        )
        for r in reqs
    ]


async def _notify_follow_request(target_id: uuid.UUID, requester_name: str) -> None:
    from app.database import AsyncSessionLocal
    from app.services.notification_service import create_notification

    async with AsyncSessionLocal() as bg_db:
        target = await bg_db.get(User, target_id)
        if target is None:
            return
        await create_notification(
            bg_db, user=target, category="social", title=f"{requester_name} wants to follow you",
            body="Accept to start messaging each other.", link_url="/follows",
        )
        await bg_db.commit()


async def _notify_follow_accepted(requester_id: uuid.UUID, target_name: str) -> None:
    from app.database import AsyncSessionLocal
    from app.services.notification_service import create_notification

    async with AsyncSessionLocal() as bg_db:
        requester = await bg_db.get(User, requester_id)
        if requester is None:
            return
        await create_notification(
            bg_db, user=requester, category="social", title=f"{target_name} accepted your follow request",
            body="You can now message each other.", link_url="/follows",
        )
        await bg_db.commit()


@router.post("/requests", response_model=FollowRequestOut, status_code=201)
async def send_follow_request(
    payload: FollowRequestCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(f"follow-request:{user.id}", limit=settings.RATE_LIMIT_FOLLOW_REQUEST_PER_HOUR, window_seconds=3600)
    if payload.target_id == user.id:
        raise ValidationAppError("You can't follow yourself.")
    target = await db.get(User, payload.target_id)
    if target is None or target.deleted_at is not None:
        raise NotFoundError("User not found.")

    # has_accepted_connection() checks both directions in one query, so this
    # single call replaces what used to be two separate inline
    # status=="accepted" checks (one on the reverse-direction row, one on
    # the forward-direction row below) — the exact "single gate" helper
    # chat.py already relies on for the same question.
    if await has_accepted_connection(db, user.id, payload.target_id):
        raise ConflictError("You're already connected with this person.")

    # Same class of check-then-insert race chat.py::start_direct_message
    # already guards against on (requester_id, target_id)'s real unique
    # constraint (uq_follow_request_pair) — without a lock, two rapid
    # duplicate submits (double-click, retry-on-timeout) can both pass the
    # "no existing row" check below before either commits, and the second
    # insert then hits the constraint as a raw, unhandled IntegrityError
    # instead of the clean ConflictError a couple of lines down.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"follow_request:{user.id}:{payload.target_id}"})

    existing = (await db.execute(
        select(FollowRequest).where(FollowRequest.requester_id == user.id, FollowRequest.target_id == payload.target_id)
    )).scalar_one_or_none()
    if existing is not None and existing.status == "pending":
        raise ConflictError("You already sent a follow request to this person.")

    if existing is not None:
        # Was declined — re-requesting resets the same row rather than erroring,
        # matching how a real social app lets you try again.
        existing.status = "pending"
        existing.responded_at = None
        request_row = existing
    else:
        request_row = FollowRequest(requester_id=user.id, target_id=payload.target_id)
        db.add(request_row)
    await db.commit()
    await db.refresh(request_row)

    background_tasks.add_task(_notify_follow_request, payload.target_id, user.full_name)
    return await _to_out(db, request_row)


@router.get("/requests/incoming", response_model=list[FollowRequestOut])
async def list_incoming_requests(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(FollowRequest).where(FollowRequest.target_id == user.id, FollowRequest.status == "pending")
        .order_by(FollowRequest.created_at.desc())
    )).scalars().all()
    return await _to_out_many(db, rows)


@router.get("/requests/outgoing", response_model=list[FollowRequestOut])
async def list_outgoing_requests(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(FollowRequest).where(FollowRequest.requester_id == user.id, FollowRequest.status == "pending")
        .order_by(FollowRequest.created_at.desc())
    )).scalars().all()
    return await _to_out_many(db, rows)


@router.post("/requests/{request_id}/accept", response_model=FollowRequestOut)
async def accept_follow_request(
    request_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(FollowRequest, request_id)
    if req is None or req.target_id != user.id:
        raise NotFoundError("Follow request not found.")
    if req.status != "pending":
        raise ConflictError(f"This request was already {req.status}.")
    req.status = "accepted"
    req.responded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(req)

    background_tasks.add_task(_notify_follow_accepted, req.requester_id, user.full_name)
    return await _to_out(db, req)


@router.post("/requests/{request_id}/decline", response_model=FollowRequestOut)
async def decline_follow_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(FollowRequest, request_id)
    if req is None or req.target_id != user.id:
        raise NotFoundError("Follow request not found.")
    if req.status != "pending":
        raise ConflictError(f"This request was already {req.status}.")
    req.status = "declined"
    req.responded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(req)
    return await _to_out(db, req)


@router.delete("/requests/{request_id}", response_model=MessageResponse)
async def cancel_follow_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(FollowRequest, request_id)
    if req is None or req.requester_id != user.id:
        raise NotFoundError("Follow request not found.")
    await db.delete(req)
    await db.commit()
    return MessageResponse(message="Follow request cancelled.")


@router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Deliberately not has_accepted_connection() here: that helper answers
    # "is this one specific pair connected?" — this endpoint needs to
    # enumerate every accepted row for the current user, a different query
    # shape entirely.
    rows = (await db.execute(
        select(FollowRequest).where(
            FollowRequest.status == "accepted",
            or_(FollowRequest.requester_id == user.id, FollowRequest.target_id == user.id),
        )
    )).scalars().all()
    out = []
    for r in rows:
        other_id = r.target_id if r.requester_id == user.id else r.requester_id
        other = await db.get(User, other_id)
        if other is None:
            continue
        profile = (await db.execute(select(Profile).where(Profile.user_id == other_id))).scalar_one_or_none()
        out.append(ConnectionOut(
            user_id=other.id, full_name=other.full_name,
            public_handle=profile.public_handle if profile else None,
            avatar_url=profile.avatar_url if profile else None,
            connected_since=r.responded_at or r.created_at,
        ))
    return out


@router.delete("/connections/{user_id}", response_model=MessageResponse)
async def remove_connection(
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Deliberately not has_accepted_connection() here: that helper only
    # returns a bool, and this endpoint needs the actual row to delete.
    row = (await db.execute(
        select(FollowRequest).where(
            FollowRequest.status == "accepted",
            or_(
                and_(FollowRequest.requester_id == user.id, FollowRequest.target_id == user_id),
                and_(FollowRequest.requester_id == user_id, FollowRequest.target_id == user.id),
            ),
        )
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundError("You're not connected with this person.")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Connection removed.")


@router.get("/search", response_model=list[PersonSearchResultOut])
async def search_people(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(20, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authenticated-only (not public) — deliberately returns name/handle/
    avatar, never email, to keep this from being a plain account-lookup-by-
    email tool for anyone who signs up. Matches on the unique @handle as
    well as full name, since the handle is how people are meant to find
    each other precisely (full names collide; handles never do)."""
    await enforce_rate_limit(f"people-search:{user.id}", limit=settings.RATE_LIMIT_PEOPLE_SEARCH_PER_MINUTE, window_seconds=60)
    like = f"%{escape_like(q)}%"
    candidates = (await db.execute(
        select(User)
        .outerjoin(Profile, Profile.user_id == User.id)
        .where(
            User.id != user.id, User.deleted_at.is_(None),
            or_(User.full_name.ilike(like), Profile.public_handle.ilike(like)),
        )
        .order_by(User.full_name).limit(limit)
    )).scalars().all()
    if not candidates:
        return []
    candidate_ids = [c.id for c in candidates]

    # Deliberately not N calls to has_accepted_connection() here: that would
    # be one query per search result. This single batched query over all
    # candidate_ids does the equivalent check for every result at once.
    relevant_requests = (await db.execute(
        select(FollowRequest).where(
            or_(
                and_(FollowRequest.requester_id == user.id, FollowRequest.target_id.in_(candidate_ids)),
                and_(FollowRequest.target_id == user.id, FollowRequest.requester_id.in_(candidate_ids)),
            )
        )
    )).scalars().all()

    def _relationship(other_id: uuid.UUID) -> str:
        for r in relevant_requests:
            if r.requester_id == user.id and r.target_id == other_id:
                return "connected" if r.status == "accepted" else ("pending_outgoing" if r.status == "pending" else "none")
            if r.target_id == user.id and r.requester_id == other_id:
                return "connected" if r.status == "accepted" else ("pending_incoming" if r.status == "pending" else "none")
        return "none"

    profiles = {
        p.user_id: p for p in (await db.execute(select(Profile).where(Profile.user_id.in_(candidate_ids)))).scalars().all()
    }
    return [
        PersonSearchResultOut(
            user_id=c.id, full_name=c.full_name,
            public_handle=profiles[c.id].public_handle if c.id in profiles else None,
            avatar_url=profiles[c.id].avatar_url if c.id in profiles else None,
            relationship=_relationship(c.id),
        )
        for c in candidates
    ]
