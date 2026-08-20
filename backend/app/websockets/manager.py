from __future__ import annotations

import contextlib
import json
import uuid
from collections import defaultdict

import structlog
from fastapi import WebSocket

from app.redis_client import get_redis

logger = structlog.get_logger("survivalschool.ws")

_CHANNEL_PREFIX = "ws:room:"


class ConnectionManager:
    """Connection registry backed by Redis pub/sub for cross-worker delivery.

    Previously a plain in-memory dict (see git history / docs/REALTIME.md):
    correct only for a single-replica deployment, since two users connected
    to different gunicorn workers (this app runs --workers 2, see
    backend/Dockerfile) could never see each other's broadcasts — there was
    no shared layer wiring the workers' independent in-memory maps
    together. broadcast() now always publishes to a Redis channel rather
    than writing to local sockets directly; a single background listener
    task (started from the app lifespan, see main.py) subscribes to every
    room channel this process has an active connection for and delivers
    incoming messages to this process's local sockets only. This naturally
    handles same-worker delivery too (Redis delivers a publish back to the
    publisher's own subscription), so there is exactly one delivery path,
    not a local-fast-path-plus-Redis-fallback split to keep in sync.
    """

    def __init__(self) -> None:
        self.rooms: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self.socket_user: dict[WebSocket, uuid.UUID] = {}
        self._pubsub = None
        self._listener_task = None

    async def connect(self, room_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        is_new_room = room_id not in self.rooms
        self.rooms[room_id].add(websocket)
        self.socket_user[websocket] = user_id
        if is_new_room and self._pubsub is not None:
            await self._pubsub.subscribe(f"{_CHANNEL_PREFIX}{room_id}")

    def disconnect(self, room_id: uuid.UUID, websocket: WebSocket) -> None:
        self.rooms[room_id].discard(websocket)
        self.socket_user.pop(websocket, None)
        if not self.rooms[room_id]:
            del self.rooms[room_id]

    async def broadcast(self, room_id: uuid.UUID, message: dict, *, exclude: WebSocket | None = None) -> None:
        # `exclude` only matters for same-process delivery (e.g. "don't echo
        # a typing event back to its sender") — encode which socket to skip
        # so every worker's listener can honor it identically, not just
        # whichever worker happened to publish.
        envelope = {"room_id": str(room_id), "message": message, "exclude_socket_id": id(exclude) if exclude else None}
        try:
            client = get_redis()
            await client.publish(f"{_CHANNEL_PREFIX}{room_id}", json.dumps(envelope))
        except Exception:
            logger.warning("ws_broadcast_publish_failed", room_id=str(room_id), exc_info=True)
            # Redis is down — fall back to local-only delivery so the app
            # degrades to single-worker-correct behavior rather than going
            # fully silent.
            await self._deliver_local(room_id, message, exclude)

    async def _deliver_local(self, room_id: uuid.UUID, message: dict, exclude: WebSocket | None) -> None:
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

    async def start_listener(self) -> None:
        """Call once from the app lifespan. Subscribes lazily per-room (see
        connect()) rather than to a single wildcard pattern, since PSUBSCRIBE
        pattern matching is measurably slower per-message than exact
        SUBSCRIBE at the message volumes a busy chat/battle room can hit."""
        client = get_redis()
        self._pubsub = client.pubsub()
        # Re-subscribe to whatever rooms already have local connections —
        # relevant only if start_listener is ever called after connections
        # exist, which doesn't happen today but keeps the method safe to
        # call at any point in the lifecycle.
        for room_id in list(self.rooms.keys()):
            await self._pubsub.subscribe(f"{_CHANNEL_PREFIX}{room_id}")
        self._listener_task = None
        import asyncio
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        assert self._pubsub is not None
        try:
            async for raw in self._pubsub.listen():
                if raw is None or raw.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(raw["data"])
                    room_id = uuid.UUID(envelope["room_id"])
                    message = envelope["message"]
                    exclude_socket_id = envelope.get("exclude_socket_id")
                except Exception:
                    logger.warning("ws_broadcast_envelope_invalid", exc_info=True)
                    continue
                exclude_ws = None
                if exclude_socket_id is not None:
                    exclude_ws = next((ws for ws in self.rooms.get(room_id, ()) if id(ws) == exclude_socket_id), None)
                await self._deliver_local(room_id, message, exclude_ws)
        except Exception:
            logger.warning("ws_listener_stopped_unexpectedly", exc_info=True)

    async def stop_listener(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()
            with contextlib.suppress(Exception):
                await self._listener_task
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.close()


manager = ConnectionManager()
