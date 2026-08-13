# Real-time chat (WebSockets)

## Endpoint

```
WS /ws/chat/{room_id}?token=<access_token>
```

Implemented in `app/websockets/chat.py`, registered directly on the FastAPI
app (`app/main.py::app.include_router(ws_chat_router)`), not nested under the
`/api/v1` REST prefix.

## Authentication and authorization

Browsers cannot set custom headers on a WebSocket handshake, so the access
token travels as a query parameter (`?token=...`) rather than an
`Authorization` header. The handler:

1. Rejects the connection with close code `4401` if the token is missing or
   fails JWT validation (`decode_access_token`).
2. Looks up `ChatMember` for `(room_id, user_id)` and rejects with close code
   `4403` if the connecting user is not a member of that room — this check
   happens **before** `websocket.accept()`, so an unauthorized client never
   even completes the handshake.

## Message flow

Every inbound frame is a JSON object with an `event` field:

| Event | Behavior |
|---|---|
| `chat.typing` | Broadcast to other room members, not persisted |
| `chat.message` | Validated (non-empty, ≤4000 chars), rejected if the sender is muted, **persisted to `chat_messages` in Postgres first**, then broadcast with the real DB-assigned `id` and `created_at` |
| `chat.read` | Broadcast read-receipt, not persisted as its own row (backed by the `message_reads` table via the REST endpoint) |

On connect/disconnect, a `presence.updated` event is broadcast to the rest of
the room.

## Why Postgres-first, not socket-first

The docstring in `chat.py` states the design intent directly: "a client that
misses the broadcast (dropped connection) can always recover full history via
`GET /api/v1/chat/rooms/{id}/messages`, so the WebSocket is never the sole
source of truth." Concretely: if the broadcast fails to reach a client
(network blip, reconnecting client, multiple tabs), no message is lost —
every message exists in the database the instant it was accepted, and the
REST history endpoint is the recovery path a reconnecting client is expected
to call.

## Connection manager

`app/websockets/manager.py` keeps an in-process map of `room_id -> set of
active WebSocket connections`. This means:

- **Single-process only.** If the backend is scaled to multiple replicas (as
  the Kubernetes manifests do — `infra/k8s/06-backend.yaml` runs 2+ replicas
  by default), two users connected to different pods will not see each
  other's broadcasts, because the in-memory `manager` isn't shared across
  processes.
- **This is a known, real limitation**, not a hidden one. Fixing it for a
  true multi-replica production deployment requires a shared pub/sub layer
  (Redis Pub/Sub is the natural choice, since Redis is already a hard
  dependency for rate limiting) so a message persisted by one replica is
  broadcast by every replica holding a connection for that room. That change
  has **not** been implemented in this build — chat works correctly for
  local/single-replica deployment (e.g. `docker compose up`) and was tested
  in that topology, but would need the Redis pub/sub layer before running
  correctly in the multi-replica Kubernetes deployment this same repo
  ships manifests for.

## What has been verified

- Room-membership authorization (member vs. non-member) exists in code and
  follows the same JWT decoding path used and tested elsewhere
  (`security/tokens.py`, exercised by the auth test suite).
- Message persistence path shares the same `AsyncSessionLocal` /
  SQLAlchemy models used throughout the REST API — no parallel/duplicate
  data path.
- End-to-end WebSocket connect → send → receive has **not** been exercised
  by an automated test in `backend/tests/` (no WebSocket test client is
  configured in this build's test suite) — this is a real gap. The code was
  reviewed manually for correctness against the FastAPI/Starlette WebSocket
  API, but "reviewed" is not the same claim as "tested," and this document
  says so explicitly.
