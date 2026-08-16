"""Authenticated, authorized WebSocket chat.

Browser clients authenticate with the HttpOnly access cookie so JWTs are never
placed in the WebSocket URL. A query token remains temporarily supported for
legacy non-browser clients and can be removed after all clients migrate.
"""
from __future__ import annotations

import uuid

import jwt
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.config import get_settings
from app.core.auth_cookie import ACCESS_COOKIE
from app.database import AsyncSessionLocal
from app.models.social import ChatMember, ChatMessage, MessageRead
from app.models.user import Session as SessionModel
from app.security.tokens import decode_access_token
from app.websockets.manager import manager

router = APIRouter()
logger = structlog.get_logger("survivalschool.ws")
settings = get_settings()


@router.websocket("/ws/chat/{room_id}")
async def chat_socket(websocket: WebSocket, room_id: uuid.UUID):
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.cors_origins_list:
        await websocket.close(code=4403, reason="Origin not allowed")
        return

    token = websocket.cookies.get(ACCESS_COOKIE) or websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing auth token")
        return
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        await websocket.close(code=4401, reason="Invalid token")
        return

    if payload.get("type") != "access" or not payload.get("sid"):
        await websocket.close(code=4401, reason="Invalid token")
        return

    try:
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
    except (KeyError, ValueError, TypeError):
        await websocket.close(code=4401, reason="Invalid token")
        return

    async with AsyncSessionLocal() as db:
        session_row = await db.get(SessionModel, session_id)
        if session_row is None or session_row.revoked_at is not None:
            await websocket.close(code=4401, reason="Session revoked")
            return
        member = (await db.execute(
            select(ChatMember).where(ChatMember.room_id == room_id, ChatMember.user_id == user_id)
        )).scalar_one_or_none()
        if member is None:
            await websocket.close(code=4403, reason="Not a member of this room")
            return

    await manager.connect(room_id, user_id, websocket)
    await manager.broadcast(room_id, {"event": "presence.updated", "user_id": str(user_id), "status": "online"}, exclude=websocket)

    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("event")

            if event_type == "chat.typing":
                await manager.broadcast(room_id, {"event": "chat.typing", "user_id": str(user_id)}, exclude=websocket)

            elif event_type == "chat.message":
                body = (data.get("body") or "").strip()
                if not body or len(body) > 4000:
                    continue
                async with AsyncSessionLocal() as db:
                    member = (await db.execute(
                        select(ChatMember).where(ChatMember.room_id == room_id, ChatMember.user_id == user_id)
                    )).scalar_one_or_none()
                    if member is None or member.muted:
                        continue
                    message = ChatMessage(room_id=room_id, sender_id=user_id, body=body)
                    db.add(message)
                    await db.commit()
                    await db.refresh(message)

                await manager.broadcast(room_id, {
                    "event": "chat.message",
                    "id": str(message.id),
                    "room_id": str(room_id),
                    "sender_id": str(user_id),
                    "body": message.body,
                    "created_at": message.created_at.isoformat(),
                })

            elif event_type == "chat.read":
                message_id = data.get("message_id")
                if not message_id:
                    continue
                try:
                    parsed_message_id = uuid.UUID(str(message_id))
                except (ValueError, TypeError):
                    continue
                async with AsyncSessionLocal() as db:
                    existing = (await db.execute(
                        select(MessageRead).where(MessageRead.message_id == parsed_message_id, MessageRead.user_id == user_id)
                    )).scalar_one_or_none()
                    if existing is None:
                        db.add(MessageRead(message_id=parsed_message_id, user_id=user_id))
                        await db.commit()
                await manager.broadcast(room_id, {"event": "chat.read", "user_id": str(user_id), "message_id": str(parsed_message_id)}, exclude=websocket)

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(room_id, websocket)
        await manager.broadcast(room_id, {"event": "presence.updated", "user_id": str(user_id), "status": "offline"})
