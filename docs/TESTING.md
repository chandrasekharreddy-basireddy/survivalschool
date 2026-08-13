# Testing

## Backend: 24 tests, all passing against real infrastructure

```bash
cd backend
source .venv/bin/activate
APP_ENV=test python -m pytest -q
# 24 passed
```

These are integration tests running against a **real local PostgreSQL 16 and
Redis 7** (not sqlite, not mocked/faked datastores) — `conftest.py` creates
the schema via the actual Alembic-managed models against a real database
connection for every test session. `NullPool` is used for the test-env
engine specifically to avoid event-loop/connection-reuse issues under
pytest-asyncio's per-test event loops (see `docs/DATABASE.md`).

| File | What it proves |
|---|---|
| `test_auth.py` (8 tests) | Weak-password rejection; full register→verify→login flow; duplicate registration conflict; generic wrong-password error; account lockout after repeated failures; refresh-token rotation and reuse-detection revoking the session; logout-all revoking every session; password reset revoking existing sessions |
| `test_rbac.py` (4 tests) | Student cannot create a course; unauthenticated request gets a real 401 (not a 403 or a silent pass); an instructor cannot publish another instructor's content without the right permission; `SUPER_ADMIN` bypasses per-permission checks |
| `test_quiz_and_certificate_flow.py` (4 tests) | **Quiz scoring ignores a client-submitted `is_correct: true`** on a wrong answer (the single most important anti-cheat test in the suite); duplicate submission of an already-submitted attempt is a no-op, not a double-score; completing a course issues a certificate that is independently verifiable via the public endpoint; gamification points/badges are computed server-side, never accepted from the client |
| `test_rate_limiting.py` (2 tests) | The Redis-backed limiter actually blocks after its configured threshold; limits are scoped per key (one user hitting a limit doesn't block a different user) |
| `test_scoring_service.py` (6 tests) | Unit tests of the pure grading functions in isolation: single-choice correct/incorrect, multiple-choice requires an exact set match (partial credit is not awarded), short-answer normalizes whitespace/case before comparing, pass/fail boundary at the configured threshold, zero-possible-points attempts never register as passed |

## What "passing" actually means here

Every test in this suite performs real HTTP requests against a real FastAPI
`TestClient`/`AsyncClient` instance, which executes real route handlers,
which run real SQLAlchemy queries against a real Postgres database, and (for
the rate-limiting tests) real Redis `INCR`/`EXPIRE` calls. Nothing in this
suite is a unit test with every dependency mocked out — the closest thing to
a pure unit test is `test_scoring_service.py`, which tests grading logic
that genuinely has no I/O.

## Running the full verification chain locally

```bash
# from backend/
source .venv/bin/activate
ruff check app tests              # lint — must be zero errors
pip-audit -r requirements.txt     # dependency vulnerability scan — must be clean
bandit -r app -ll                 # security static analysis, medium+ severity
alembic upgrade head              # apply schema to whatever DB DATABASE_URL points at
APP_ENV=test python -m pytest -q  # the 24 tests above
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
  the Starlette WebSocket API, not exercised by an automated client.
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
  suite) — the frontend's only automated verification is
  `npm run lint` + `npm run typecheck` + a successful production build.
  This is a real gap for a platform this size and should be prioritized
  before this becomes a long-lived production codebase, not just an MVP.
- **No cascade-delete test** exists for the `ondelete="CASCADE"` foreign
  keys described in `docs/DATABASE.md` — the schema declares the behavior,
  but no test asserts it end-to-end.
