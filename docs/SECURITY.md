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
  by `test_login_wrong_password_is_generic` and
  `test_login_nonexistent_email_matches_wrong_password_response`.
- **Timing-safe login**: the response *body* being identical for "wrong
  password" and "no such account" isn't the whole story — a second security
  pass on this codebase found that the "no such account" branch was
  returning immediately, skipping the (deliberately slow) Argon2id verify
  that the "wrong password" branch pays, which made the two paths
  distinguishable by response latency alone. Fixed by calling
  `verify_password_dummy()` — a real Argon2id verify against a fixed dummy
  hash — on the not-found branch, so both paths cost the same regardless of
  which email is being probed. See `app/security/passwords.py` and
  `tests/test_passwords.py` (which asserts the dummy verify does real,
  non-trivial hashing work rather than being a no-op — a live A/B timing
  comparison would be flaky under CI jitter, so the test checks an absolute
  floor instead).
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
  adding a new role never requires touching route code. This build added
  `certificates.manage` (certificate revocation, ADMIN-only),
  `files.upload` (STUDENT/INSTRUCTOR/ADMIN), and `timetable.manage`
  (INSTRUCTOR/ADMIN — create/update/delete timetable entries). The four other
  new-feature endpoint groups (discussions, practice, instructor analytics,
  search) deliberately do **not** get new blanket permissions — access is
  checked directly against real ownership/enrollment relationships instead
  (is this user enrolled in / the instructor of / the author of the specific
  resource being touched), which keeps the permission surface from growing
  for every feature and makes the access rule impossible to get right for one
  course and wrong for another.
- **401 vs 403 on discussion reads**: an initial version of the discussions
  read-access check always raised 401 ("not authenticated") for any denial,
  even when the caller *was* authenticated but simply not enrolled in — or
  the instructor of — the course (e.g., a different instructor requesting
  another instructor's unpublished-course discussions). That collapses two
  different failure modes into one status code, which matters for clients
  distinguishing "log in" from "you don't have access." Fixed with a
  `_require_read_access()` helper (`app/api/v1/discussions.py`) that raises
  `AuthenticationError` (401) only when `user is None`, and
  `AuthorizationError` (403) otherwise.
- **A permission-escalation bug found and fixed while building
  `published_only=false` draft-course visibility** (instructors need to see
  their own unpublished drafts on their dashboard): the first
  implementation gated the "see drafts beyond your own" escape hatch on
  `courses.read` — a permission every instructor already holds for the
  unrelated purpose of viewing *published* courses. That would have let any
  instructor browse every other instructor's private, unpublished course
  content. This was not caught by manual review; it was caught by the test
  written specifically for this feature
  (`test_unpublished_courses_are_not_leaked_to_anonymous_or_other_instructors`
  in `tests/test_new_endpoints.py`), which failed on first run because a
  second instructor account really could see the first instructor's draft.
  Fixed by gating the escape hatch on `system.manage` instead (ADMIN/
  SUPER_ADMIN only); every other caller is scoped to their own drafts.
  Re-ran the test, confirmed it passes. Recorded here rather than quietly
  fixed and omitted, consistent with "don't hide things."

## Data integrity / anti-cheat

- **Server-authoritative scoring**: client-submitted correctness/score fields
  are never trusted — see `docs/ARCHITECTURE.md` and
  `test_quiz_scoring_ignores_client_submitted_correctness`.
- **Idempotent submission**: duplicate submit of an already-submitted attempt
  does not re-score or double-award points — verified by
  `test_duplicate_quiz_submission_is_idempotent`.
- **Concurrent-submit race, closed**: a second security pass found that the
  idempotency check above only works if two concurrent submits for the same
  attempt are serialized against each other — without that, two requests
  (double-click, a client retry racing the original, two open tabs) could
  both read `status == "in_progress"` before either committed, both grade,
  and both award points/badges. `app/api/v1/quizzes.py::submit_attempt` and
  `app/api/v1/exams.py::submit_exam_attempt` now fetch the attempt with
  `with_for_update=True`, which takes a row lock so a second concurrent
  request blocks until the first commits, then correctly observes
  `status == "submitted"` and takes the idempotent early return. This is
  proven, not just asserted: `tests/test_concurrency.py` fires 8 genuinely
  concurrent submit requests at the same attempt through the real ASGI app
  and checks the points ledger reflects exactly one grading pass — this test
  was confirmed to actually fail without the fix (reverted the lock,
  reran, watched it fail, restored the fix, reran, watched it pass) before
  being kept as a permanent regression test.
- **Achievement/certificate insert races**: the same class of race exists
  one level down — `evaluate_and_award_badges()` and `issue_certificate()`
  both do a select-then-insert that a concurrent request can race. The
  database's unique constraints (`uq_achievement_student_badge`,
  `uq_certificate_student_course`) already prevented a duplicate row from
  ever being persisted, but the *losing* request used to surface as an
  unhandled `IntegrityError` (a raw 500) instead of gracefully treating "lost
  the race" the same as "already awarded." Both now wrap the insert in a
  `SAVEPOINT` (`db.begin_nested()`) and catch `IntegrityError`, so the
  losing request's own transaction (which may include other legitimate
  work, like the quiz/exam result that triggered the check) still commits
  normally.
- **Exam question options never leak `is_correct`** to student-facing
  responses (`schemas` layer strips it) before submission.
- **Gamification points/badges are entirely server-computed** — no endpoint
  accepts a client-supplied point value. Verified by
  `test_gamification_points_and_badges_are_server_computed`.

## Contests, AI practice, bulk import, attendance

- **Exam integrity monitoring is log-only, never punitive.** `PUT
  /exams/attempts/{attempt_id}/events` records tab-blur/fullscreen-exit/
  copy/paste/right-click events to `ExamAttempt.flagged_events`, but no code
  path ever uses that log to auto-submit or auto-fail an attempt — it only
  surfaces for instructor review via `GET
  /exams/{exam_id}/attempts/flagged`. This is deliberate, documented in code
  comments in `app/api/v1/exams.py`: events like these have real false-
  positive causes (a dropped network connection, an OS notification
  stealing window focus) that have nothing to do with cheating, so treating
  them as automatic evidence would unfairly penalize honest students. The
  events endpoint is capped at 200 events/attempt and always returns
  `{"logged": true|false}` rather than failing the request.
- **AI-generated practice questions are structurally isolated from the real
  question bank and never award points.** `ai_mock_sessions`/
  `ai_generated_questions`/`ai_generated_question_options`/`ai_mock_answers`
  (`app/models/ai_practice.py`) share no foreign key or code path with
  `questions`/`question_options`, the table quizzes/exams/contests actually
  draw from — an AI-generated question cannot end up in a quiz, exam, or
  contest by construction, not just by convention. Submitting an AI mock
  session is graded server-side (same never-trust-the-client principle as
  every other assessment path) but awards zero gamification points and never
  contributes to a certificate or grade, matching the existing practice-mode
  pattern (`docs/API.md`).
- **Bulk question import is all-or-nothing and permission+ownership
  gated.** `POST /questions/bulk-import` requires `quiz.create` or
  `exam.manage` plus verified ownership of the target course (or
  `system.manage`) — an instructor cannot bulk-import questions into another
  instructor's course. A commit (`dry_run=false`) only writes anything if
  every row in the uploaded file validates; if any row fails, nothing is
  inserted, closing off a partial-import state where an instructor can't
  tell which rows actually landed.
- **Attendance check-in codes expire after 15 minutes.**
  `CODE_VALIDITY_MINUTES = 15` in `app/services/attendance_service.py` — a
  check-in code is only valid for 15 minutes from when the session was
  opened (or reopened, which rotates a fresh code), limiting how long a code
  shared aloud in a classroom stays usable. Opening a session is also
  restricted to the timetable entry's actual scheduled weekday and an active
  term, so an instructor can't open attendance for a class that isn't
  scheduled today.

## Client IP resolution (`X-Forwarded-For` trust)

A second security pass on this codebase found that `get_client_ip()`
(`app/dependencies.py`) trusted the client-supplied `X-Forwarded-For` header
unconditionally, with no check that the request actually came through a
trusted reverse proxy. That value fed directly into the per-IP login/register
rate limiter and the audit-log/session IP address fields — meaning any
direct caller could set an arbitrary `X-Forwarded-For` value to get a fresh
rate-limit bucket per request (defeating brute-force throttling) or to
poison the IP address recorded in security audit logs.

Fixed with a new `TRUST_PROXY_HEADERS` setting, **default `false`**: the app
now uses the raw TCP peer address (which a client cannot spoof) unless this
deployment is explicitly known to sit behind a reverse proxy that
sets/overwrites the header itself. The Kubernetes manifests set it to `true`
(`infra/k8s/01-configmap.yaml`) since that deployment always sits behind
ingress-nginx; `docker-compose.yml`/local dev leave it `false` since the
backend is directly reachable there. **If you deploy this behind a different
reverse proxy topology, set this explicitly** — leaving it `false` behind a
real proxy means every request appears to come from the proxy's IP (a
usability bug: one bad actor could exhaust the shared rate-limit bucket for
everyone), and leaving it `true` without a real proxy in front reopens the
spoofing issue this fix closes. See `docs/ENVIRONMENT.md`.

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
- **HTTPS enforcement**: `HTTPSRedirectMiddleware` (`app/core/middleware.py`)
  redirects plain-HTTP requests to HTTPS at the app layer, as defense in
  depth on top of ingress-level TLS termination. It follows the exact same
  spoofing-safe pattern already established for `X-Forwarded-For`: it only
  trusts the `X-Forwarded-Proto` header when `TRUST_PROXY_HEADERS=True` (the
  same setting, not a second one to keep in sync); with it `False` (the
  default), the middleware checks the actual connection scheme, which a
  client cannot spoof. `/api/v1/health` and `/api/v1/live` are exempted so
  Kubernetes probes (which hit the pod over plain HTTP inside the cluster
  network) don't get redirected and fail.
- **Metrics endpoint**: `GET /metrics` (Prometheus text format, via
  `prometheus-fastapi-instrumentator`) is **not** app-layer authenticated —
  it relies entirely on network-layer restriction (a `NetworkPolicy`/
  ingress rule that only allows the cluster's Prometheus scraper to reach
  it). If you expose this backend directly to the internet without that
  network restriction in place, `/metrics` is publicly readable. This is
  called out explicitly in `docs/DEPLOYMENT.md` — it is not wired to
  require a bearer token today.

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
- Frontend: `npm audit` reports **zero vulnerabilities** as of this session.
  This was previously a known, deliberately-deferred gap (Next.js 14.2.x had
  21 open advisories — DoS, XSS, SSRF, and cache-poisoning classes — none of
  which are fixed anywhere in the 14.x line; Vercel's security backports stop
  at 15.5.x). A second security pass upgraded to Next.js 15.5.23 + React
  19.2.8 rather than deferring again, specifically chosen as the *lowest*
  version satisfying every advisory's fixed-version threshold (some needed
  ≥15.5.10, the last needed ≥15.5.21) — a smaller jump than the latest
  major (16.3.1) that npm's own `audit fix --force` suggested. This was safe
  to verify fully: every page in this app is a client component
  (`"use client"`) using the `useParams`/`useSearchParams` hooks rather than
  server-component `params`/`searchParams` props, so Next 15's breaking
  change in that area doesn't touch this codebase at all — confirmed by
  grepping every `page.tsx` before starting the upgrade, not assumed.
  `npm run lint`, `npm run typecheck`, and `npm run build` all pass
  post-upgrade with zero errors across all 12 routes. Two more vulnerabilities
  survived the Next.js bump itself — a `sharp` (image processing) advisory
  and a nested `postcss` copy bundled inside `next`'s own `node_modules`,
  neither of which npm's normal dependency resolution reaches since they're
  transitive/optional deps of `next` itself — closed via an `overrides`
  block in `package.json` forcing both to patched versions (`sharp` is
  unused by this app in the first place; grepped for `next/image` and found
  no usage anywhere in `src/`).
- Three packages were added to `requirements.txt` for the certificate/
  monitoring/upload work: `weasyprint==69.0` (server-side PDF rendering —
  its system-library dependencies, `libpango`/`libcairo`/`libgdk-pixbuf`/
  `libmagic1`, are installed in `backend/Dockerfile`'s runtime stage;
  imported lazily inside `generate_certificate_pdf_bytes()` so a deployment
  missing those libraries returns a clean 503 instead of crashing the whole
  app at import time), `prometheus-fastapi-instrumentator==8.1.0` (metrics),
  and `python-magic==0.4.27` (real content-sniffing for file uploads, also
  needs `libmagic1` at runtime). `pip-audit -r requirements.txt` was re-run
  after adding them and still reports zero known vulnerabilities.
- Backend and frontend container images are scanned with Trivy in CI
  (`.github/workflows/ci.yml`, `docker-build` job) for fixable CRITICAL/HIGH
  CVEs (`--ignore-unfixed`); findings are reported in the job log (report-only
  for now, so unpatched upstream base-image CVEs don't wedge the pipeline).
  SBOMs for both images are generated with Syft. A gitleaks secret-scan job
  runs on every push/PR.
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
  attack. Combined with `TRUST_PROXY_HEADERS` being misconfigured (see
  above), these are the two remaining ways an attacker could blunt
  login/register throttling; both are documented, deliberate tradeoffs with
  a stated default that fails toward safety, not silent gaps.
- `start_exam_attempt`/`start_attempt` (starting a new attempt, as opposed to
  submitting one) still has a narrower, lower-severity race: two concurrent
  "start" calls for the same student+quiz could both pass the
  `max_attempts` check and both create an attempt row, in the rare case a
  student double-clicks "start" right at their attempt limit. Worst case is
  one extra attempt, not a scoring/points integrity issue like the submit
  race that was fixed — noted here rather than fixed in this pass since the
  submit-side race was the one with real integrity impact.
- No WAF / DDoS layer is provisioned — that's an infrastructure decision for
  wherever this is actually deployed (Cloudflare, AWS WAF, etc.), not
  something the application code can provide.
- Automated dependency updates are configured via Dependabot
  (`.github/dependabot.yml`) for the pip (backend) and npm (frontend)
  ecosystems, so `requirements.txt`/`package.json` receive update PRs rather
  than silently drifting.
- The `Profile.avatar_url` / `Course.cover_image_url` fields are stored and
  returned to clients as plain strings with no server-side validation that
  they're actually image URLs.
- **Update**: a real file-upload endpoint now exists (`POST /files`,
  `app/api/v1/files.py`), closing what was previously an open gap. It does
  real content-sniffing with `python-magic` against the actual uploaded
  bytes — checked against an explicit MIME-to-extension allowlist
  (`_ALLOWED_MIME_TO_EXT`) — rather than trusting the client-supplied
  `Content-Type` header, and the storage key is server-generated (a UUID),
  never derived from the client-supplied filename, so path traversal isn't
  possible through this endpoint. Verified by `tests/test_new_endpoints.py`:
  a renamed executable with a spoofed image `Content-Type` is rejected on
  its real content, and a genuine image is accepted. Access control:
  `files.upload` permission gates who can upload (STUDENT, INSTRUCTOR,
  ADMIN all hold it); a private file is only readable by its owner or an
  admin, verified by a dedicated test for both a different authenticated
  user and an anonymous caller. Storage is local-disk only in this build —
  the cloud option is `STORAGE_BACKEND: Literal["local", "supabase"]` — the
  `supabase` backend uploads to Supabase Storage (`SUPABASE_STORAGE_URL` /
  `SUPABASE_SERVICE_ROLE_KEY`); there is no `s3` backend (see
  `docs/DEPLOYMENT.md`).
- No penetration test or third-party security audit has been performed —
  everything above is internal static/dependency scanning, integration
  testing, and two internal security review passes (one during initial
  build, a second deeper pass specifically hunting for logic bugs and races
  that static tools don't catch), not an external adversarial review.
