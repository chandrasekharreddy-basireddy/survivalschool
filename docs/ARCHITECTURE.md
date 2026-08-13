# Architecture

## System overview

Survival School is a monorepo with three deployable components plus one external
automation instance:

```
frontend/   Next.js 14 (App Router, TypeScript, Tailwind) — student/instructor/admin UI
backend/    FastAPI (Python 3.11, async) — REST API + WebSocket chat + background worker
infra/      docker-compose, Dockerfiles, GitHub Actions CI, Kubernetes manifests, n8n workflow reference
```

Data stores: PostgreSQL 16 (system of record, 44 tables) and Redis 7 (rate-limit
counters and caching). An external n8n Cloud instance handles outbound
notification fan-out; Sarvam AI provides the AI tutor's language model.

```
┌──────────────┐      HTTPS/WSS      ┌───────────────────┐
│  Next.js UI  │ ──────────────────► │   FastAPI backend  │
└──────────────┘                     │  (2+ replicas)      │
                                      └────────┬───────────┘
                                               │
                        ┌──────────────────────┼───────────────────┐
                        ▼                      ▼                   ▼
                 ┌─────────────┐        ┌────────────┐     ┌──────────────┐
                 │ PostgreSQL  │        │   Redis    │     │ background   │
                 │ (system of  │        │ (rate      │     │ worker       │
                 │  record)    │        │  limits)   │     │ (streaks,    │
                 └─────────────┘        └────────────┘     │  inactivity) │
                                                             └──────────────┘
                        │                                          │
                        │  outbound events (fire-and-forget)       │
                        ▼                                          ▼
                 ┌─────────────────┐                    ┌────────────────────┐
                 │  n8n Cloud       │                    │  Sarvam AI          │
                 │  Event Router    │                    │  chat completions   │
                 │  workflow        │                    │  (AI tutor)         │
                 └─────────────────┘                    └────────────────────┘
```

## Backend layout (`backend/app/`)

| Package | Responsibility |
|---|---|
| `api/v1/` | 15 route modules (auth, users, courses, lessons, quizzes, exams, certificates, gamification, notifications, chat, ai, analytics, admin, health) — see `docs/API.md` |
| `models/` | SQLAlchemy 2.0 async ORM models, one file per domain (user, lms, assessment, gamification, certificate, social, ai, system) |
| `schemas/` | Pydantic request/response schemas, kept separate from ORM models so API contracts don't leak internal columns (`is_correct` on question options, password hashes, etc.) |
| `services/` | Business logic with no HTTP concerns: scoring, gamification, certificates, email, analytics, audit, n8n events, AI provider, rate limiting |
| `security/` | Password hashing (Argon2id), JWT encode/decode |
| `core/` | Cross-cutting middleware, structured logging, typed exception hierarchy |
| `websockets/` | Authenticated WebSocket chat + connection manager |
| `workers/` | Standalone background-job process (separate container/Deployment from the API) |
| `dependencies.py` | FastAPI dependency functions: `get_current_user`, `require_permission(...)`, `require_role(...)` — every protected route composes these, so authorization is enforced centrally, not per-handler |

## Key design decisions

**Server-authoritative scoring.** `services/scoring_service.py` is the only code
path that decides whether an answer is correct. Quiz/exam submit endpoints accept
only raw `selected_option_ids` / `text_answer` from the client — never a score or
correctness flag — and grade against `QuestionOption.is_correct`, which is never
serialized to a student-facing response before submission. Verified by
`tests/test_quiz_and_certificate_flow.py::test_quiz_scoring_ignores_client_submitted_correctness`,
which submits an intentionally-wrong client-side `is_correct: true` and asserts
the server ignores it.

**RBAC is backend-enforced, not role-name-enforced.** Permissions
(`courses.create`, `quiz.manage`, `analytics.view`, …) are the unit of
authorization; roles are just named permission bundles (see `app/seed.py`).
`require_permission("courses.create")` on a route means exactly that — any role
holding that permission passes, not just `INSTRUCTOR`. `SUPER_ADMIN` is the one
explicit bypass, checked first in `dependencies.py`.

**Idempotent submission.** Exam/quiz attempts carry a `status` column
(`in_progress` → `submitted`) plus, for exams, a `submission_client_token`.
Re-submitting an already-submitted attempt is a no-op that returns the original
result rather than double-scoring or double-awarding points.

**AIProvider abstraction.** `services/ai_provider.py` defines an `AIProvider`
interface with two implementations: `MockAIProvider` (deterministic, used by
default and in CI) and `SarvamAIProvider` (real HTTP client against Sarvam's
REST API). Route handlers and the rest of the business logic depend only on the
interface, selected once via `AI_PROVIDER=mock|sarvam`. See `docs/AI.md` for the
honest status of the Sarvam integration.

**Automation is decoupled and non-blocking.** `services/n8n_service.emit_event()`
fires a webhook to the n8n Event Router workflow after a state change has
already committed (registration, enrollment, quiz/exam completion, certificate
issuance). Failures are logged and swallowed — n8n being down never blocks or
rolls back a user-facing request. See `docs/N8N.md`.

**WebSocket is not the source of truth.** Chat messages are written to
Postgres (`chat_messages`) before being broadcast. A client that reconnects
after a dropped WebSocket recovers full history via
`GET /api/v1/chat/rooms/{id}/messages` — the socket is a delivery mechanism,
not storage. See `docs/REALTIME.md`.

## Frontend layout (`frontend/src/`)

Next.js 14 App Router. Pages under `src/app/` map directly to routes:
`login`, `register`, `forgot-password`, `reset-password`, `verify-email`,
`dashboard`, `courses`, `courses/[slug]`, `certificates`,
`certificates/verify`, `admin`. Auth state is a token pair (access + refresh)
kept in `localStorage`; a shared `fetch` wrapper attaches the access token and
transparently retries once through `/api/v1/auth/refresh` on a 401 before
surfacing the error to the caller.

## Request lifecycle (example: submitting a quiz)

1. Client `POST /api/v1/quizzes/attempts/{attempt_id}/submit` with raw answers only.
2. `dependencies.get_current_verified_user` validates the JWT, checks the
   session hasn't been revoked, loads the user with roles+permissions eagerly
   (`selectinload`, avoiding N+1 and lazy-load-outside-async-context errors).
3. Route handler loads the attempt, verifies it belongs to the caller and is
   still `in_progress`.
4. `scoring_service.grade_answer()` grades each answer server-side against the
   question bank; nothing from the request body influences correctness.
5. Points are awarded and badges evaluated (`gamification_service`), all inside
   the same DB transaction as the attempt's `status` flip to `submitted`.
6. `analytics_service.track_event()` records the event (best-effort; never
   raises into the request).
7. `n8n_service.emit_event("quiz.completed", …)` fires after commit.
8. Response returns the computed score — the only score the client ever sees.
