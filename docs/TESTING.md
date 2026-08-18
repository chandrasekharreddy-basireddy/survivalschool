# Testing

## Backend: 136 tests, all passing against real infrastructure

```bash
cd backend
source .venv/bin/activate
APP_ENV=test python -m pytest -q
# 70 passed
```

These are integration tests running against a **real local PostgreSQL 16 and
Redis 7** (not sqlite, not mocked/faked datastores) — `conftest.py` creates
the schema via the actual Alembic-managed models against a real database
connection for every test session. `NullPool` is used for the test-env
engine specifically to avoid event-loop/connection-reuse issues under
pytest-asyncio's per-test event loops (see `docs/DATABASE.md`).

| File | What it proves |
|---|---|
| `test_auth.py` (9 tests) | Weak-password rejection; full register→verify→login flow; duplicate registration conflict; generic wrong-password error (both the response body *and*, via `test_login_nonexistent_email_matches_wrong_password_response`, that a nonexistent email produces an identical response to a wrong password); account lockout after repeated failures; refresh-token rotation and reuse-detection revoking the session; logout-all revoking every session; password reset revoking existing sessions |
| `test_passwords.py` (3 tests) | The login-timing-attack mitigation actually does real Argon2id work rather than being a no-op — see `docs/SECURITY.md` for why this checks an absolute time floor rather than comparing two live measurements (comparative timing assertions are flaky under CI jitter) |
| `test_rbac.py` (4 tests) | Student cannot create a course; unauthenticated request gets a real 401 (not a 403 or a silent pass); an instructor cannot publish another instructor's content without the right permission; `SUPER_ADMIN` bypasses per-permission checks |
| `test_quiz_and_certificate_flow.py` (4 tests) | **Quiz scoring ignores a client-submitted `is_correct: true`** on a wrong answer (the single most important anti-cheat test in the suite); duplicate submission of an already-submitted attempt is a no-op, not a double-score; completing a course issues a certificate that is independently verifiable via the public endpoint; gamification points/badges are computed server-side, never accepted from the client |
| `test_concurrency.py` (2 tests) | **Genuinely concurrent** submits (`asyncio.gather`, 8-way) for the same quiz/exam attempt only grade and award points once — proves the `with_for_update` row-lock fix actually closes the race, not just that the code looks correct. This test was confirmed to fail when the lock was temporarily reverted, then pass once restored, before being kept as a regression test. |
| `test_rate_limiting.py` (2 tests) | The Redis-backed limiter actually blocks after its configured threshold; limits are scoped per key (one user hitting a limit doesn't block a different user) |
| `test_scoring_service.py` (6 tests) | Unit tests of the pure grading functions in isolation: single-choice correct/incorrect, multiple-choice requires an exact set match (partial credit is not awarded), short-answer normalizes whitespace/case before comparing, pass/fail boundary at the configured threshold, zero-possible-points attempts never register as passed |
| `test_new_endpoints.py` (14 tests) | The second-pass audit response (see `docs/STATUS.md`): course quiz/exam listing + pagination via `X-Total-Count`; quiz/exam attempt history; exam review only unlocks after submit (never mid-exam); certificate grade/score/skills are computed from real attempt data and the certificate can be revoked (and a non-admin is rejected trying); the certificate PDF endpoint returns real, well-formed PDF bytes; admin user management (list/search, deactivate — and a deactivated user is immediately locked out — reactivate); expanded system-health detail; audit-log filtering; file upload rejects a disguised executable via real content-sniffing (not the client-supplied header) and accepts a valid image; a private file is inaccessible to a different user and to anonymous requests; unpublished courses are never visible to anonymous callers or to a *different* instructor, only to their owner (or an admin); leaderboard N+1 fix still returns correctly ranked results |
| `test_new_features.py` (14 tests) | The fourth-pass 5-feature build (see `docs/STATUS.md`): timetable conflict detection rejects an overlapping instructor/room booking and the `.ics` export parses back into valid `VEVENT`/`RRULE` data; a non-enrolled student cannot post to a course's discussions but an enrolled one can, instructor replies are flagged server-side, upvoting is idempotent under a repeated toggle, only the course instructor/admin can resolve a thread; a practice session sourced from bookmarks or from real past mistakes grades through the same server-authoritative scoring service as quizzes/exams but awards **zero** gamification points; instructor analytics are denied to a different course's instructor and the CSV export contains real per-question rows; global search returns a published course and a discussion on a published course, but never surfaces anything from an unpublished one |
| `test_contests_ai_practice_import_integrity_attendance.py` (12 tests) | The fifth-pass 5-subsystem build (see `docs/STATUS.md`): contest creation is admin-only (`contests.manage`); a contest attempt/leaderboard/finalize flow awards top-3 finishers points and a `ContestCertificate`; the contest scheduler's `occurrence_key` prevents a duplicate contest being created for the same slot; an AI mock practice session is generated and graded server-side and awards zero gamification points; AI-generated questions never appear in the real question bank used by quizzes/exams; bulk CSV import previews then commits; a bad row makes the whole bulk import fail with nothing inserted (all-or-nothing); a non-owner instructor is rejected from importing into another instructor's course; XLSX import works the same as CSV; exam integrity events (tab-blur, copy/paste, etc.) are logged and reviewable by the course's instructor without auto-failing the attempt; opening an attendance session requires the actual scheduled weekday; the attendance check-in-code flow and instructor manual marking both work |

## What "passing" actually means here

Every test in this suite performs real HTTP requests against a real FastAPI
`TestClient`/`AsyncClient` instance, which executes real route handlers,
which run real SQLAlchemy queries against a real Postgres database, and (for
the rate-limiting tests) real Redis `INCR`/`EXPIRE` calls. Nothing in this
suite is a unit test with every dependency mocked out — the closest thing to
a pure unit test is `test_scoring_service.py`/`test_passwords.py`, which
test pure functions that genuinely have no I/O (grading logic, password
hashing).

`test_concurrency.py` deserves a specific callout: it's the one place in
this suite that tests for the *absence* of a race condition, which is a
different (and easier to get wrong) kind of test than asserting a single
request behaves correctly. The methodology that makes it trustworthy: the
test was written, confirmed to fail against the pre-fix code (by temporarily
reverting the fix), then confirmed to pass against the fixed code, before
being committed as a permanent regression test. A concurrency test that was
only ever run against already-fixed code can't tell you whether it would
actually have caught the bug — this one demonstrably would have.

## Running the full verification chain locally

```bash
# from backend/
source .venv/bin/activate
ruff check app tests              # lint — must be zero errors
pip-audit -r requirements.txt     # dependency vulnerability scan — must be clean
bandit -r app -ll                 # security static analysis, medium+ severity
alembic upgrade head              # apply schema to whatever DB DATABASE_URL points at
APP_ENV=test python -m pytest -q  # the 136 tests above
```

```bash
# from frontend/
npm ci
npm run lint
npm run typecheck
npm run build                     # production build — must succeed
```

Both of these command sequences are exactly what `.github/workflows/ci.yml`
runs on every push/PR (see `docs/CI_CD.md`).

## Coverage

`pytest-cov` is installed and CI runs with `--cov=app
--cov-report=term-missing --cov-report=xml`, uploading `coverage.xml` as a
build artifact. No specific coverage percentage threshold is enforced (no
`--cov-fail-under` flag) — coverage is visible, not gated. This is a
deliberate scope choice for an MVP timeline, not an oversight; enforcing a
hard threshold is a reasonable follow-up once the team decides what number
is meaningful for this codebase.

## What is explicitly NOT tested (known gaps, not hidden)

- **WebSocket chat** has no automated test coverage (see `docs/REALTIME.md`)
  — connect/auth/broadcast/persist behavior was manually reviewed against
  the Starlette WebSocket API, not exercised by an automated client. The
  frontend `/chat/[roomId]` client (`src/lib/ws.ts`) was manually exercised
  against the real backend WebSocket during this build (see below), but that
  was a one-time manual pass, not a repeatable automated test.
- **Sarvam AI live calls** and **n8n backend→webhook HTTP calls** are
  untested from this sandbox due to network egress restrictions — see
  `docs/AI.md` and `docs/N8N.md`. Both are exercised through their
  local/mock code paths only.
- **Docker image builds** are not tested in this sandbox (registry network
  blocked) — validated structurally via `docker compose config` only. CI's
  `docker-build` job will actually build and Trivy-scan images the first
  time it runs on GitHub Actions infrastructure, which has real registry
  access.
- **No load/performance testing** has been performed.
- **No frontend component/e2e tests** exist yet (no Jest/Playwright/Cypress
  suite committed to the repo) — the frontend's only *automated, repeatable*
  verification is `npm run lint` + `npm run typecheck` + a successful
  production build. This is a real gap for a platform this size and should
  be prioritized before this becomes a long-lived production codebase, not
  just an MVP.

  What *was* done in this session, one time, manually, with Playwright
  against the actual running stack (real Postgres/Redis, real FastAPI
  backend, real `next start` production build) — not committed as a suite,
  so it doesn't protect against regressions, but real evidence the pages
  work as built, not just that they compile: registered and verified two
  real accounts through the API, promoted one to INSTRUCTOR by hand,
  created a real course/section/lesson/quiz through the actual instructor
  endpoints, enrolled a student, answered the quiz correctly, completed the
  lesson (which triggered real certificate issuance with a computed grade
  and score), then loaded `/certificates/view/{number}` and
  `/certificates/me` and `/profile` and `/leaderboard` and `/dashboard` in a
  real Chromium browser — logged in through the actual `/login` form, not a
  seeded session — and confirmed zero console/page errors and correct
  rendering (screenshots retained). Also downloaded
  `/certificates/{number}/pdf` and confirmed it's a real, valid PDF
  (`file` reports `PDF document, version 1.7`). The next real step here is
  turning that manual pass into a committed Playwright suite that runs in CI
  — tracked, not done.
- **No cascade-delete test** exists for the `ondelete="CASCADE"` foreign
  keys described in `docs/DATABASE.md` — the schema declares the behavior,
  but no test asserts it end-to-end.
