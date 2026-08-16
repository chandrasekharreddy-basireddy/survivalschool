"""Authenticated, authorized WebSocket chat (spec sections 19, 47).

Every connection must present a valid access token as a query param (browsers
can't set custom headers on the WS handshake) and must be a member of the
room it's joining — unauthorized rooms are rejected before `accept()`.
Messages are always persisted to Postgres first, then broadcast; a client
that misses the broadcast (dropped connection) can always recover full
history via GET /api/v1/chat/rooms/{id}/messages, so the WebSocket is never
the sole source of truth (spec: "Never rely solely on the WebSocket
connection for message persistence.").
"""
from __future__ import annotations

import uuid

import jwt
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.social import ChatMember, ChatMessage, MessageRead
from app.models.system import Session as SessionModel
from app.security.tokens import decode_access_token
from app.websockets.manager import manager

router = APIRouter()
logger = structlog.get_logger("survivalschool.ws")


@router.websocket("/ws/chat/{room_id}")
async def chat_socket(websocket: WebSocket, room_id: uuid.UUID):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing auth token")
        return
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        await websocket.close(code=4401, reason="Invalid token")
        return

    # V-07: Validate token type and session revocation — prevents use of
    # refresh tokens or revoked-session tokens for WebSocket connections.
    if payload.get("type") != "access":
        await websocket.close(code=4401, reason="Invalid token type")
        return

    user_id = uuid.UUID(payload["sub"])
    session_id = payload.get("sid")
    if not session_id:
        await websocket.close(code=4401, reason="Malformed token")
        return

    async with AsyncSessionLocal() as db:
        # Check session not revoked
        session_row = await db.get(SessionModel, uuid.UUID(session_id))
        if session_row is None or session_row.revoked_at is not None:
            await websocket.close(code=4401, reason="Session has been revoked")
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
                # Previously this only broadcast the event and never persisted
                # it — MessageRead rows were written by the REST endpoint
                # (POST /chat/rooms/{id}/messages/{id}/read) but nothing ever
                # called it, so read receipts silently never survived a page
                # reload. Persist here too, idempotently, so the two paths
                # agree and a reload can recover read state.
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
