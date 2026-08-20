"""Elimination battle WebSocket — read-only from the client's side by
design: all state-changing actions (start battle, submit answer) go
through the authenticated REST endpoints in api/v1/elimination.py, which
enforce the server-authoritative deadline/grading logic in
elimination_service.py. This socket exists purely to push
battle.round_released / battle.answer_result / battle.round_resolved /
battle.completed events to connected participants in real time — the
same "Postgres/REST-first, then broadcast" principle chat.py already
uses, so a client that misses an event (dropped connection) can always
recover current state via GET /elimination/battles/{id} and
/elimination/battles/{id}/participants rather than depending on the
socket as its only source of truth.
"""
from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.elimination import EliminationParticipant
from app.models.user import Session as SessionModel
from app.security.tokens import decode_access_token
from app.websockets.manager import manager

router = APIRouter()


@router.websocket("/ws/elimination/{battle_id}")
async def elimination_socket(websocket: WebSocket, battle_id: uuid.UUID):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing auth token")
        return
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        await websocket.close(code=4401, reason="Invalid token")
        return
    if payload.get("type") != "access":
        await websocket.close(code=4401, reason="Invalid token type")
        return

    user_id = uuid.UUID(payload["sub"])
    session_id = payload.get("sid")
    if not session_id:
        await websocket.close(code=4401, reason="Malformed token")
        return

    async with AsyncSessionLocal() as db:
        session_row = await db.get(SessionModel, uuid.UUID(session_id))
        if session_row is None or session_row.revoked_at is not None:
            await websocket.close(code=4401, reason="Session has been revoked")
            return
        participant = (await db.execute(
            select(EliminationParticipant).where(EliminationParticipant.battle_id == battle_id, EliminationParticipant.user_id == user_id)
        )).scalar_one_or_none()
        if participant is None:
            await websocket.close(code=4403, reason="Not a participant in this battle")
            return

    await manager.connect(battle_id, user_id, websocket)
    try:
        while True:
            # Client sends nothing meaningful over this socket — all actions
            # are REST calls. Just keep the connection alive and detect
            # disconnects; any received frame is ignored.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(battle_id, websocket)
