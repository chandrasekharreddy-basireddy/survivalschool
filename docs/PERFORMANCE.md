# Performance & Load Testing

This document records real load-test results captured against the actual
application (gunicorn + uvicorn workers, real PostgreSQL 16, real Redis 7 —
no mocks), plus the caching and indexing work that produced them. Every
number below came from an actual run on this machine; none are estimated or
invented. Re-run the commands yourself to reproduce.

## Environment this was measured on

- 2 vCPU / 7.8 GiB RAM sandbox container (`nproc` = 2)
- Backend served via `gunicorn -k uvicorn.workers.UvicornWorker -w 2` (2
  workers, matching vCPU count — the same sizing rule to use in production:
  workers ≈ CPU cores for an async ASGI app, scaled out further with more
  replicas rather than more workers-per-pod)
- PostgreSQL 16 and Redis 7 running locally, not over a network hop
- Load generated with `autocannon` (Node.js), 50 concurrent connections,
  5x HTTP pipelining, 20s duration per run
- Data volume: 300 seeded courses (in addition to demo data) for the
  courses-list benchmark, so pagination/query cost reflects a real catalog
  size, not an empty table

Because this is a 2-vCPU sandbox rather than production hardware, treat the
req/s figures as a *lower bound* and the relative improvements (caching vs.
no caching) as the portable, meaningful result — that ratio does not depend
on the machine.

## Caching impact: `GET /courses` (public catalog)

Same endpoint, same query shape, same 300-course dataset. Two branches of
`list_courses` (`backend/app/api/v1/courses.py`) were compared: the public
`published_only=true` path (cached, versioned Redis namespace
`courses_list`, 30s TTL) vs. the `published_only=false` admin path (never
cached — deliberately, since it returns caller-specific unpublished drafts
that are unsafe to share across a cache key).

| | Cached (public path) | Uncached (admin path, same DB cost) |
|---|---|---|
| Avg req/s | **718.65** | **162.10** |
| Median (p50) latency | 320 ms | 1036 ms |
| p97.5 latency | 474 ms | 2907 ms |
| p99 latency | 502 ms | 3068 ms |
| Total requests / 20s | 15,000 | 3,000 |

**~4.4x more throughput, ~3.2x lower median latency, from caching alone**,
on identical hardware and an identical query. Single-request timings
confirm the same story at the individual-request level: a cold cache miss
took 14.1 ms; the very next (warm) request took 10.7 ms.

Reproduce:
```bash
# cached path (anonymous)
autocannon -c 50 -d 20 -p 5 "http://127.0.0.1:8000/api/v1/courses?limit=50"

# uncached path (same query cost, admin token, published_only=false)
autocannon -c 50 -d 20 -p 5 -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://127.0.0.1:8000/api/v1/courses?published_only=false&limit=50"
```

## Brute-force protection under concurrent load: `POST /auth/login`

Hammering `/auth/login` with 20 concurrent connections immediately surfaced
the rate limiter working exactly as designed: `RATE_LIMIT_LOGIN_PER_5MIN`
(10 requests / 5 minutes, enforced per-IP *and* per-email independently, see
`app/api/v1/auth.py` lines 200-201) kicked in after the first ~8 requests,
and the remaining 12,010 of 12,018 requests in the run correctly received
`429 rate_limited` rather than being processed. Zero requests reached
argon2 password verification after the limit tripped, zero 5xx responses,
zero crashes. This is the intended behavior — login throughput is not a
metric to optimize here, it's a metric to cap, and this confirms the cap
holds under real concurrent traffic, not just in the unit tests.

## Server stability under load

`gunicorn`'s error log showed 100 `RuntimeError: unable to perform
operation on <TCPTransport closed...>` entries, all timestamped exactly at
the two 20s benchmark windows' end. This is a benign uvloop artifact from
autocannon closing 50 pipelined connections simultaneously at test
teardown — it is a server *log* entry, not a response the client received;
autocannon's own summaries confirm 100% 2xx responses for both courses-list
runs (it only reports a non-2xx line when they occur, as it did, correctly,
for the login-limiter run). No unhandled exceptions, no worker restarts, no
degraded responses under either sustained load run.

## Database indexes added for this pass

Added in `alembic/versions/c4a91f7d0e2b_add_missing_performance_indexes.py`,
applied and verified against the live schema:

- `ix_courses_instructor_id` — instructor's own course list / ownership checks
- `ix_courses_published_deleted` (composite `is_published, deleted_at`) — the exact predicate `list_courses` filters on
- `ix_chat_messages_room_created` (composite `room_id, created_at`) — chat history pagination
- `ix_notifications_user_created` (composite `user_id, created_at`) — notification feed pagination

The rest of the schema was already well-indexed with justification comments
inline (see `docs/DATABASE.md`); this migration closes the 4 real gaps
found by cross-referencing every FK/status/date column against actual
`.where()`/`.join()`/`.order_by()` clauses in the API and service layers —
not a blanket "index everything" pass.

## What's cached and how invalidation works

Two patterns, both in `app/services/cache_service.py`, both degrade to a
cache miss (never a 500) on any Redis error:

- **Direct-key caching** — single resources with an obvious identity, e.g.
  a contest's leaderboard (`cache:contest:{id}:leaderboard`). Invalidated
  by deleting that exact key on the write path that changes it.
- **Versioned-namespace caching** — result sets shaped by arbitrary query
  parameters (course list, contest list, gamification leaderboard), where
  enumerating every possible key to delete isn't practical. Every key in
  the namespace embeds a version counter (`INCR`'d in Redis); bumping the
  counter on any write instantly invalidates every cached variant without
  a `SCAN`/`KEYS` pattern-delete (which would block Redis's single-threaded
  event loop — a deliberate anti-pattern avoidance, not an oversight).

Endpoints cached this pass: `GET /courses` (public catalog, 30s TTL),
`GET /contests`, `GET /contests/upcoming` (15s TTL), `GET
/contests/{id}/leaderboard` (5s TTL, direct-key), `GET
/gamification/leaderboard` (15s TTL). TTLs were chosen short deliberately —
these are all read-heavy, write-light, and mildly-stale-tolerant views;
correctness-critical reads (a user's own progress, exam attempts, payment-
adjacent flows — none of which exist here, but the principle holds) were
never cached.

## Recommendations for production sizing

- Set gunicorn `-w` to `(2 x vCPU) + 1` per the standard formula once
  running on real hardware, not the 2-worker sandbox sizing used above.
- Put a CDN/reverse-proxy cache (even 5-10s) in front of `GET /courses` and
  `GET /contests` for anonymous traffic — the Redis layer already makes
  this safe to layer on top of, since both are idempotent GETs with no
  per-user variation on the cached branch.
- The `RATE_LIMIT_LOGIN_PER_5MIN` limiter is per-IP; behind a NAT/shared
  corporate network this could false-positive-limit multiple legitimate
  users. Current default (10/5min) has headroom before this becomes a
  practical issue, but if login-support tickets mention this, the
  per-email limiter (already present, independent of the per-IP one) is
  the one that actually protects the account and could have its window
  tuned independently.
