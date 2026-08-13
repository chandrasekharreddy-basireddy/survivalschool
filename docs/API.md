# API reference

Base path: `{API_V1_PREFIX}` = `/api/v1`. Interactive docs are served live at
`/api/docs` (Swagger UI) and `/api/redoc` when the backend is running — those
are generated directly from the FastAPI route definitions and Pydantic
schemas below, so they're always in sync with the actual code; this document
is a human-readable index, not a duplicate source of truth.

All request/response bodies are defined in `app/schemas/*.py`. All endpoints
below except `health`/`live`/`ready` and `auth/register|login|refresh|forgot-password|reset-password|verify-email|resend-verification`
and `certificates/verify/{number}` and `certificates/{number}/qr` require a
valid `Authorization: Bearer <access_token>` header; most additionally
require a specific permission (see `docs/SECURITY.md`).

## Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | General health summary |
| GET | `/live` | Kubernetes liveness probe — process up, no dependency checks |
| GET | `/ready` | Kubernetes readiness probe — checks DB connectivity, returns 503 if not ready |

## Auth (`/auth`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create account (rate-limited, enforces password policy) |
| POST | `/auth/verify-email` | Consume email verification token |
| POST | `/auth/resend-verification` | Re-send verification email (rate-limited) |
| POST | `/auth/login` | Exchange credentials for access+refresh token pair |
| POST | `/auth/refresh` | Rotate refresh token, issue new access token |
| POST | `/auth/logout` | Revoke current session |
| POST | `/auth/logout-all` | Revoke every session for the current user |
| POST | `/auth/forgot-password` | Request password reset email (rate-limited) |
| POST | `/auth/reset-password` | Consume reset token, set new password, revoke existing sessions |
| GET | `/auth/me` | Current user profile |

## Users (`/users`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/users/me/profile` | Own profile detail |
| PATCH | `/users/me/profile` | Update own profile |
| GET | `/users` | List users (`users.read`) |
| POST | `/users/{user_id}/roles/{role_name}` | Grant a role (`users.update`) |

## Courses (`/courses`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/courses` | List published courses |
| POST | `/courses` | Create course (`courses.create`) |
| GET | `/courses/{course_id}` | Course detail with sections/lessons |
| PATCH | `/courses/{course_id}` | Update course (`courses.update`) |
| POST | `/courses/{course_id}/publish` | Publish |
| POST | `/courses/{course_id}/unpublish` | Unpublish |
| DELETE | `/courses/{course_id}` | Delete (`courses.delete`) |
| POST | `/courses/{course_id}/sections` | Add a section (`lessons.manage`) |
| POST | `/courses/{course_id}/enroll` | Self-enroll; emits `course.enrolled` to n8n |
| GET | `/courses/me/enrollments` | Own enrollments |

## Lessons (`/lessons`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/lessons/sections/{section_id}` | Add lesson to a section (`lessons.manage`) |
| POST | `/lessons/{lesson_id}/complete` | Mark complete; awards points, evaluates badges, recalculates course progress, issues a certificate + emits `certificate.issued` if this completes the course |

## Quizzes (`/quizzes`, question bank at `/questions`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/quizzes` | Create quiz (`quiz.create`) |
| POST | `/quizzes/{quiz_id}/publish` | Publish (`quiz.manage`) |
| POST | `/quizzes/{quiz_id}/attempts` | Start an attempt — returns questions **without** `is_correct` |
| GET | `/quizzes/{quiz_id}/attempts/current` | Resume an in-progress attempt |
| POST | `/quizzes/attempts/{attempt_id}/submit` | Server-side grading; ignores any client-submitted score |

## Exams (`/exams`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/exams` | Create exam (`exam.manage`) |
| POST | `/exams/{exam_id}/publish` | Publish |
| POST | `/exams/{exam_id}/attempts` | Start a timed, server-deadlined attempt (rate-limited: `RATE_LIMIT_EXAM_START_PER_HOUR`) |
| GET | `/exams/attempts/{attempt_id}/questions` | Fetch this attempt's fixed question order |
| PUT | `/exams/attempts/{attempt_id}/autosave` | Periodic autosave of in-progress answers |
| POST | `/exams/attempts/{attempt_id}/submit` | Idempotent submit (`submission_client_token` + status check) |

## Certificates (`/certificates`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/certificates/me` | Own earned certificates |
| GET | `/certificates/verify/{certificate_number}` | **Public**, unauthenticated — PII-minimized verification |
| GET | `/certificates/{certificate_number}/qr` | QR code pointing at the public verification URL |

## Gamification (`/gamification`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/gamification/me` | Own points, streak, badges |
| GET | `/gamification/leaderboard` | Ranked leaderboard |

## Notifications (`/notifications`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/notifications` | List own notifications |
| POST | `/notifications/{notification_id}/read` | Mark read |
| GET | `/notifications/preferences` | Get channel preferences |
| PATCH | `/notifications/preferences` | Update channel preferences |

## Chat (`/chat`, + WebSocket)

| Method | Path | Purpose |
|---|---|---|
| GET | `/chat/rooms` | List own rooms |
| POST | `/chat/rooms` | Create a room |
| GET | `/chat/rooms/{room_id}/messages` | History (also the WebSocket-recovery path) |
| POST | `/chat/rooms/{room_id}/messages/{message_id}/read` | Mark read |
| POST | `/chat/rooms/{room_id}/messages/{message_id}/moderate` | Moderate (`chat.moderate`) |
| WS | `/ws/chat/{room_id}?token=<access_token>` | Real-time send/receive — see `docs/REALTIME.md` |

## AI assistant (`/ai`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/ai/conversations` | List own conversations |
| POST | `/ai/conversations` | Start a conversation |
| GET | `/ai/conversations/{conversation_id}/messages` | History |
| POST | `/ai/conversations/{conversation_id}/messages` | Send a message; routed through `AIProvider` — see `docs/AI.md` |

## Analytics (`/analytics`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/analytics/events` | Client-side event ingestion (202 Accepted, fire-and-forget) |

## Admin (`/admin`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/dashboard` | Aggregate platform metrics (`analytics.view`) |
| GET | `/admin/audit-logs` | Audit log stream (`system.manage`) |
| GET | `/admin/system-health` | DB/Redis/n8n/Sarvam configuration status |

## Error format

All errors go through a typed exception hierarchy (`app/core/exceptions.py`):
`AppError` subclasses (`AuthenticationError`, `AuthorizationError`,
`NotFoundError`, `ConflictError`, `ValidationError`, …) render as
`{"error": {"code": "...", "message": "..."}}` with the matching HTTP status.
An unhandled exception is caught by a catch-all handler and never leaks a
stack trace to the client — it returns a generic 500 and logs the real error
server-side via structlog.
