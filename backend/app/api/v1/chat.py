from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.social import ChatMember, ChatMessage, ChatRoom, MessageRead
from app.models.user import User
from app.services.social_graph_service import has_accepted_connection

router = APIRouter(prefix="/chat", tags=["chat"])


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # "direct" is deliberately excluded here — a 1:1 room can only be created
    # through POST /chat/dm/{user_id}, which enforces the follow-accepted
    # gate. Without that, this endpoint would let any authenticated user
    # message any other user by just naming them in member_ids.
    room_type: str = Field(default="course", pattern=r"^(course|announcement)$")
    course_id: uuid.UUID | None = None
    # Bounded: any authenticated user can create a room, so an unbounded
    # member list lets one request fan out to arbitrarily many membership rows.
    member_ids: list[uuid.UUID] = Field(default=[], max_length=500)


class RoomOut(BaseModel):
    id: uuid.UUID
    name: str
    room_type: str
    # Populated only for room_type == "direct" — the other participant, so
    # the frontend can show a person's name instead of a generic room name.
    other_user_id: uuid.UUID | None = None
    other_user_name: str | None = None

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    sender_id: uuid.UUID | None
    body: str
    created_at: datetime
    is_deleted: bool

    model_config = {"from_attributes": True}


async def _assert_member(db: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID) -> None:
    member = (await db.execute(
        select(ChatMember).where(ChatMember.room_id == room_id, ChatMember.user_id == user_id)
    )).scalar_one_or_none()
    if member is None:
        raise AuthorizationError("You are not a member of this room.")


@router.get("/rooms", response_model=list[RoomOut])
async def my_rooms(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatRoom).join(ChatMember, ChatMember.room_id == ChatRoom.id).where(ChatMember.user_id == user.id)
    )
    rooms = result.scalars().all()
    direct_room_ids = [room.id for room in rooms if room.room_type == "direct"]

    # Batched instead of one ChatMember query + one db.get(User) per direct
    # room: this endpoint backs the chat sidebar, loaded on every visit, so
    # an N-room inbox previously meant up to 2N extra round trips.
    other_name_by_room: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
    if direct_room_ids:
        other_members = (await db.execute(
            select(ChatMember.room_id, ChatMember.user_id).where(
                ChatMember.room_id.in_(direct_room_ids), ChatMember.user_id != user.id,
            )
        )).all()
        other_user_ids = {row.user_id for row in other_members}
        names_by_id = {
            u.id: u.full_name
            for u in (await db.execute(select(User).where(User.id.in_(other_user_ids)))).scalars().all()
        } if other_user_ids else {}
        for room_id, other_user_id in other_members:
            if other_user_id in names_by_id:
                other_name_by_room[room_id] = (other_user_id, names_by_id[other_user_id])

    out = []
    for room in rooms:
        other_id, other_name = other_name_by_room.get(room.id, (None, None))
        out.append(RoomOut(id=room.id, name=room.name, room_type=room.room_type, other_user_id=other_id, other_user_name=other_name))
    return out


@router.post("/rooms", response_model=RoomOut, status_code=201)
async def create_room(payload: RoomCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    room = ChatRoom(name=payload.name, room_type=payload.room_type, course_id=payload.course_id, created_by=user.id)
    db.add(room)
    await db.flush()
    db.add(ChatMember(room_id=room.id, user_id=user.id, role="moderator"))
    for member_id in payload.member_ids:
        db.add(ChatMember(room_id=room.id, user_id=member_id))
    await db.commit()
    await db.refresh(room)
    return room


@router.post("/dm/{other_user_id}", response_model=RoomOut, status_code=201)
async def start_direct_message(other_user_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The only way a direct room gets created — gated on an accepted follow
    request existing between the two users (see social_graph_service.py).
    Idempotent: if a direct room between exactly these two already exists,
    it's reused instead of creating a duplicate."""
    if other_user_id == user.id:
        raise ValidationAppError("You can't message yourself.")
    other_user = await db.get(User, other_user_id)
    if other_user is None or other_user.deleted_at is not None:
        raise NotFoundError("User not found.")
    if not await has_accepted_connection(db, user.id, other_user_id):
        raise AuthorizationError("You can only message someone who has accepted a follow request with you.")

    # The find-or-create below is a check-then-insert with no DB-level
    # uniqueness on (user pair, room_type='direct'). Without a lock, both
    # users hitting "Message" for each other at nearly the same moment
    # (realistic right after a follow-accept notification fires for both)
    # can each pass the "no existing room" check before either commits,
    # creating two separate direct rooms for the same pair. Order the two
    # user ids before hashing so the lock key is the same regardless of who
    # calls this endpoint first.
    pair_key = "|".join(sorted([str(user.id), str(other_user_id)]))
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"chat_dm:{pair_key}"})

    my_room_ids = select(ChatMember.room_id).where(ChatMember.user_id == user.id)
    existing = (await db.execute(
        select(ChatRoom).join(ChatMember, ChatMember.room_id == ChatRoom.id).where(
            ChatRoom.room_type == "direct", ChatRoom.id.in_(my_room_ids), ChatMember.user_id == other_user_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return RoomOut(id=existing.id, name=existing.name, room_type=existing.room_type, other_user_id=other_user.id, other_user_name=other_user.full_name)

    room = ChatRoom(name=other_user.full_name, room_type="direct", created_by=user.id)
    db.add(room)
    await db.flush()
    db.add(ChatMember(room_id=room.id, user_id=user.id, role="member"))
    db.add(ChatMember(room_id=room.id, user_id=other_user_id, role="member"))
    await db.commit()
    return RoomOut(id=room.id, name=room.name, room_type=room.room_type, other_user_id=other_user.id, other_user_name=other_user.full_name)


@router.get("/rooms/{room_id}/messages", response_model=list[MessageOut])
async def list_messages(room_id: uuid.UUID, before: datetime | None = Query(None), limit: int = Query(50, le=200),
                         user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _assert_member(db, room_id, user.id)
    stmt = select(ChatMessage).where(ChatMessage.room_id == room_id)
    if before:
        stmt = stmt.where(ChatMessage.created_at < before)
    result = await db.execute(stmt.order_by(ChatMessage.created_at.desc()).limit(limit))
    return list(reversed(result.scalars().all()))


@router.post("/rooms/{room_id}/messages/{message_id}/read", status_code=204)
async def mark_message_read(room_id: uuid.UUID, message_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _assert_member(db, room_id, user.id)
    existing = (await db.execute(
        select(MessageRead).where(MessageRead.message_id == message_id, MessageRead.user_id == user.id)
    )).scalar_one_or_none()
    if existing is None:
        db.add(MessageRead(message_id=message_id, user_id=user.id))
        await db.commit()


@router.post("/rooms/{room_id}/messages/{message_id}/moderate", status_code=204)
async def moderate_message(room_id: uuid.UUID, message_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not (user.has_permission("chat.moderate") or user.has_role("SUPER_ADMIN")):
        raise AuthorizationError("Requires chat.moderate permission.")
    message = await db.get(ChatMessage, message_id)
    if message is None or message.room_id != room_id:
        raise NotFoundError("Message not found.")
    message.is_deleted = True
    await db.commit()
