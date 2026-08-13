from __future__ import annotations

import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """In-process connection registry — a plain in-memory dict, no Redis or
    other cross-process backing store.

    KNOWN LIMITATION (see docs/REALTIME.md): this only tracks sockets held
    open on *this* backend process. In a multi-replica deployment (the
    Kubernetes manifests in infra/k8s/ default the backend to 2+ replicas),
    two users connected to different pods will NOT see each other's
    broadcasts, because there is no shared pub/sub layer wiring the
    replicas' in-memory maps together. Redis pub/sub is the natural fix
    (Redis is already a hard dependency for rate limiting) but has not been
    implemented. Correct today only for single-replica deployments, e.g.
    `docker compose up`."""

    def __init__(self) -> None:
        self.rooms: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self.socket_user: dict[WebSocket, uuid.UUID] = {}

    async def connect(self, room_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self.rooms[room_id].add(websocket)
        self.socket_user[websocket] = user_id

    def disconnect(self, room_id: uuid.UUID, websocket: WebSocket) -> None:
        self.rooms[room_id].discard(websocket)
        self.socket_user.pop(websocket, None)
        if not self.rooms[room_id]:
            del self.rooms[room_id]

    async def broadcast(self, room_id: uuid.UUID, message: dict, *, exclude: WebSocket | None = None) -> None:
        dead = []
        for ws in self.rooms.get(room_id, set()):
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(room_id, ws)


manager = ConnectionManager()
