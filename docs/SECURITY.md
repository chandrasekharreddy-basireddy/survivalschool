# Security

This document describes what is actually implemented and verified in this
codebase, not a generic security checklist. Every claim below is backed by a
specific file and, where applicable, a specific passing test.

## Authentication

- **Password hashing**: Argon2id via `argon2-cffi` (`app/security/passwords.py`).
  Passwords are never stored, logged, or compared in plaintext.
- **Password policy**: minimum 10 characters, requires uppercase, lowercase,
  digit, and symbol (`app/security/passwords.py::PASSWORD_POLICY_MESSAGE`),
  enforced server-side at registration. Verified by
  `tests/test_auth.py::test_register_rejects_weak_password`.
- **Access tokens**: JWT (`PyJWT`, HS256), 15-minute default TTL
  (`ACCESS_TOKEN_TTL_MINUTES`), carries `sub` (user id) and `sid` (session id).
- **Refresh tokens**: opaque random tokens, SHA-256 hashed before storage
  (`refresh_tokens` table never holds a usable token), rotated on every use.
  Reusing an already-rotated (dead) refresh token revokes the entire session —
  verified by `tests/test_auth.py::test_refresh_token_rotation_and_reuse_detection`.
- **Session revocation**: logging out, "logout all sessions", and a password
  reset all revoke sessions server-side (`sessions.revoked_at`), which
  immediately invalidates every access token tied to that session even before
  its JWT `exp` elapses (checked on every request in `dependencies.get_current_user`).
  Verified by `test_logout_all_revokes_sessions` and
  `test_password_reset_revokes_existing_sessions`.
- **Account lockout**: 5 failed login attempts locks the account for 15 minutes
  (`MAX_FAILED_LOGIN_ATTEMPTS`, `ACCOUNT_LOCK_MINUTES`). Verified by
  `test_account_locks_after_repeated_failures`.
- **Generic failure messages**: wrong password and non-existent email return
  the same generic error, not "user not found" vs "wrong password" — verified
  by `test_login_wrong_password_is_generic`.
- **Email verification**: required before a user can access verified-only
  endpoints (`dependencies.get_current_verified_user`); tokens expire after
  `EMAIL_VERIFICATION_TTL_HOURS` (default 24h).

## Authorization (RBAC)

- Enforced exclusively on the backend via `dependencies.require_permission(...)`
  / `require_role(...)` — a hidden frontend button is never the only barrier.
  Verified by `tests/test_rbac.py` (student cannot create a course, unauthenticated
  requests get a real 401, instructors can't publish other instructors' content
  without the right permission, `SUPER_ADMIN` bypasses per-permission checks).
- Permissions are decoupled from role names (`app/seed.py::PERMISSIONS`,
  `ROLE_PERMISSIONS`) — six roles (`STUDENT`, `INSTRUCTOR`, `MODERATOR`,
  `SUPPORT`, `ADMIN`, `SUPER_ADMIN`) map to a shared permission vocabulary, so
  adding a new role never requires touching route code.

## Data integrity / anti-cheat

- **Server-authoritative scoring**: client-submitted correctness/score fields
  are never trusted — see `docs/ARCHITECTURE.md` and
  `test_quiz_scoring_ignores_client_submitted_correctness`.
- **Idempotent submission**: duplicate submit of an already-submitted attempt
  does not re-score or double-award points — verified by
  `test_duplicate_quiz_submission_is_idempotent`.
- **Exam question options never leak `is_correct`** to student-facing
  responses (`schemas` layer strips it) before submission.
- **Gamification points/badges are entirely server-computed** — no endpoint
  accepts a client-supplied point value. Verified by
  `test_gamification_points_and_badges_are_server_computed`.

## Rate limiting

- Redis-backed fixed-window limiter (`app/services/rate_limit_service.py`),
  scoped per (IP or user, action) key. Thresholds are configurable via
  `RATE_LIMIT_REGISTER_PER_HOUR`, `RATE_LIMIT_LOGIN_PER_5MIN`,
  `RATE_LIMIT_RESEND_VERIFY_PER_HOUR`, `RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR`,
  `RATE_LIMIT_EXAM_START_PER_HOUR`.
- **Fails open, not closed**: if Redis is unreachable, requests are allowed
  through rather than the app going fully unavailable — a deliberate
  availability-over-strictness tradeoff, documented in
  `rate_limit_service.py`. This means a Redis outage removes brute-force
  protection until Redis recovers; that tradeoff should be revisited before
  a security-sensitive production launch (see "Known gaps" below).
- Verified by `tests/test_rate_limiting.py` (blocks after threshold, scoped
  correctly per key).

## Transport / headers

- `SecurityHeadersMiddleware` (`app/core/middleware.py`) adds standard
  hardening headers to every response.
- CORS is explicit-allowlist (`CORS_ORIGINS`), not wildcard, in any
  environment where it's configured correctly.
- TLS termination is expected at the ingress/load balancer (see
  `infra/k8s/09-ingress.yaml`, `docker-compose.yml` does not terminate TLS
  itself — put a reverse proxy or cloud load balancer in front of it for any
  non-localhost deployment).

## Secrets handling

- `.env` is gitignored (`.gitignore`) and was `chmod 600`ed in this session's
  working copy; the repository ships only `.env.example` with placeholder
  values.
- `Settings.validate_for_production()` (`app/config.py`) fails fast at startup
  when `APP_ENV=production` and mandatory production config is missing or
  invalid (DB pointing at localhost, console email backend, missing Sarvam
  key when `AI_PROVIDER=sarvam`, a JWT secret under 32 characters).
- Kubernetes secrets are a template only (`infra/k8s/02-secret.yaml.example`),
  never committed with real values — see `infra/k8s/README.md`.

## Dependency scanning

- Backend: `pip-audit` reports **zero known vulnerabilities** as of this
  session (verified by direct execution — see `docs/CI_CD.md` for the exact
  command run in CI). `fastapi`, `starlette`, `pyjwt`, `python-multipart`,
  `jinja2`, `python-dotenv`, `pytest`, `uvicorn`, and `gunicorn` were all
  bumped to patched versions during this build specifically to close
  vulnerabilities `pip-audit` originally flagged.
- Frontend: `npm audit` flags advisories tied to the Next.js 14.x line and
  the transitive dependency tree is broad; the direct `postcss` dependency
  was bumped to a patched version (8.5.26) during this build. A major-version
  upgrade to Next.js 16 was deliberately deferred — see "Known gaps" below.
- Backend container images are scanned with Trivy in CI
  (`.github/workflows/ci.yml`, `docker-build` job) — this has not yet run
  against a real build, since this sandbox cannot push to a container
  registry (see `docs/DEPLOYMENT.md`).
- `bandit` (Python static security linter) reports zero medium/high severity
  findings against `app/`; two low-severity findings (a password-policy
  *message string* it heuristically flags as a hardcoded password, and an
  intentional broad `except Exception` in the analytics tracker that
  deliberately never raises) were reviewed and are not real issues — the
  analytics one was still tightened to log the swallowed exception instead of
  silently discarding it.

## Static analysis

- `ruff check app tests` passes with zero errors (`pyproject.toml` config:
  `E`, `F`, `W`, `I` rule sets).
- `mypy`/strict typing is **not** configured in this build — Python code
  relies on `from __future__ import annotations` and type hints throughout,
  but there is no CI-enforced type checker for the backend. This is a real
  gap, listed below.

## Known gaps (explicitly not done, not hidden)

- No mypy/pyright static type checking gate in CI for the backend.
- Rate limiter fails open on Redis outage (see above) — acceptable for an
  MVP, worth reconsidering for a public production launch under active
  attack.
- No WAF / DDoS layer is provisioned — that's an infrastructure decision for
  wherever this is actually deployed (Cloudflare, AWS WAF, etc.), not
  something the application code can provide.
- No automated dependency-update bot (Dependabot/Renovate) is configured —
  the versions in `requirements.txt`/`package.json` are a snapshot as of this
  build and will drift.
- Next.js major-version security advisories are not resolved (deferred, not
  fixed) — see `docs/CI_CD.md` and the frontend section above.
- No penetration test or third-party security audit has been performed —
  everything above is internal static/dependency scanning and integration
  testing, not an external adversarial review.
