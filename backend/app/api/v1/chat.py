from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.social import ChatMember, ChatMessage, ChatRoom, MessageRead
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    room_type: str = Field(default="direct", pattern=r"^(direct|course|announcement)$")
    course_id: uuid.UUID | None = None
    # Bounded: any authenticated user can create a room, so an unbounded
    # member list lets one request fan out to arbitrarily many membership rows.
    member_ids: list[uuid.UUID] = Field(default=[], max_length=500)


class RoomOut(BaseModel):
    id: uuid.UUID
    name: str
    room_type: str

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
    return result.scalars().all()


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
