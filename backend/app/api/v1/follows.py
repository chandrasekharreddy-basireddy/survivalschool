from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(prefix="/follows", tags=["follows"])


async def _to_out(db: AsyncSession, req: FollowRequest) -> FollowRequestOut:
    requester = await db.get(User, req.requester_id)
    target = await db.get(User, req.target_id)
    return FollowRequestOut(
        id=req.id, requester_id=req.requester_id, requester_name=requester.full_name if requester else "Unknown",
        target_id=req.target_id, target_name=target.full_name if target else "Unknown",
        status=req.status, created_at=req.created_at, responded_at=req.responded_at,
    )


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
    if payload.target_id == user.id:
        raise ValidationAppError("You can't follow yourself.")
    target = await db.get(User, payload.target_id)
    if target is None or target.deleted_at is not None:
        raise NotFoundError("User not found.")

    reverse = (await db.execute(
        select(FollowRequest).where(FollowRequest.requester_id == payload.target_id, FollowRequest.target_id == user.id)
    )).scalar_one_or_none()
    if reverse is not None and reverse.status == "accepted":
        raise ConflictError("You're already connected with this person.")

    existing = (await db.execute(
        select(FollowRequest).where(FollowRequest.requester_id == user.id, FollowRequest.target_id == payload.target_id)
    )).scalar_one_or_none()
    if existing is not None and existing.status == "pending":
        raise ConflictError("You already sent a follow request to this person.")
    if existing is not None and existing.status == "accepted":
        raise ConflictError("You're already connected with this person.")

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
    return [await _to_out(db, r) for r in rows]


@router.get("/requests/outgoing", response_model=list[FollowRequestOut])
async def list_outgoing_requests(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(FollowRequest).where(FollowRequest.requester_id == user.id, FollowRequest.status == "pending")
        .order_by(FollowRequest.created_at.desc())
    )).scalars().all()
    return [await _to_out(db, r) for r in rows]


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
            user_id=other.id, full_name=other.full_name, avatar_url=profile.avatar_url if profile else None,
            connected_since=r.responded_at or r.created_at,
        ))
    return out


@router.delete("/connections/{user_id}", response_model=MessageResponse)
async def remove_connection(
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    """Authenticated-only (not public) — deliberately returns name/avatar,
    never email, to keep this from being a plain account-lookup-by-email
    tool for anyone who signs up."""
    like = f"%{q}%"
    candidates = (await db.execute(
        select(User).where(User.id != user.id, User.deleted_at.is_(None), User.full_name.ilike(like))
        .order_by(User.full_name).limit(limit)
    )).scalars().all()
    if not candidates:
        return []
    candidate_ids = [c.id for c in candidates]

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
            avatar_url=profiles[c.id].avatar_url if c.id in profiles else None,
            relationship=_relationship(c.id),
        )
        for c in candidates
    ]
