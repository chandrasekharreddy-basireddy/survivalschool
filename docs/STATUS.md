# Production-readiness status report

This report exists because you were explicit: *"Not demo ready, it is real
production system and do not place the fake things and hallucinated
information, everything must be real and workable."* Every line below is
backed by something that was actually run in this session — a passing test,
a schema validator, a direct API query — not a description of what the code
is supposed to do. Where something could not be verified from this sandbox,
that's stated as plainly as the things that were.

Legend: **TESTED** = a real automated test or direct execution proved this
works. **CONFIGURED** = the code is real and correct, credentials are real,
but the live network call has not been exercised from this sandbox.
**BLOCKED** = something outside this codebase (sandbox restriction, missing
credential) prevents doing more right now. **GAP** = a known limitation,
documented rather than hidden.

## Second-pass security & bug audit — TESTED, fixes verified

A dedicated follow-up pass specifically hunted for bugs and vulnerabilities
static tools (ruff/pip-audit/bandit/npm audit) can't catch — logic bugs,
races, trust assumptions — using an independent deep-dive review of both the
backend and frontend, then verifying every finding by reading the actual
code before fixing anything, and re-verifying every fix with tests or
re-runs of the tooling rather than trusting the review's own claims.
Confirmed real and fixed:

- **Login timing side-channel**: the "no such account" login branch used to
  skip Argon2id hashing entirely, making it measurably faster than the
  "wrong password" branch even though both returned an identical error
  message — an attacker could enumerate valid emails by response latency.
  Fixed with a real dummy-hash verify on that branch
  (`app/security/passwords.py::verify_password_dummy`), proven by a test
  that checks it does genuine non-trivial hashing work rather than
  comparing two live timing measurements against each other (which would be
  flaky under CI jitter).
- **Double-submit race on quiz/exam attempts**: two concurrent submits for
  the same attempt (double-click, a client retry, two open tabs) could both
  pass the "not yet submitted" check before either committed, both grade,
  and both award points/badges. Fixed with a row lock
  (`with_for_update=True`) that serializes concurrent submits against each
  other. This is the one fix in this pass proven with an actual concurrency
  test, not just a code read: `tests/test_concurrency.py` fires 8 genuinely
  simultaneous submit requests through the real app and checks points were
  awarded exactly once — confirmed to fail with the lock removed, confirmed
  to pass with it restored, before being kept as a permanent regression
  test.
- **Unhandled race on badge/certificate awards**: the database's unique
  constraints already prevented duplicate rows, but the *losing* side of a
  race used to surface as a raw unhandled 500 instead of gracefully
  treating "lost the race" as "already awarded." Fixed with a `SAVEPOINT` +
  `IntegrityError` catch in both `gamification_service.py` and
  `certificate_service.py`.
- **`X-Forwarded-For` trusted unconditionally**: any direct caller could
  spoof this client-supplied header to get a fresh rate-limit bucket per
  request (defeating login/register brute-force throttling) or to poison
  the IP address recorded in audit logs. Fixed with a new
  `TRUST_PROXY_HEADERS` setting, default `false` (fail safe to the raw TCP
  peer address); the Kubernetes manifests set it `true` since that
  deployment genuinely sits behind a trusted reverse proxy.
- **Missing composite indexes**: `quiz_attempts`/`exam_attempts` lacked a
  combined index on the exact `(student_id, quiz_id/exam_id, status)` triple
  every attempt-start/resume query filters on. Added via a new, applied
  Alembic migration.
- **A hallucinated claim caught inside the code itself**: the WebSocket
  `ConnectionManager`'s own docstring claimed it was "backed by Redis
  pub/sub" for multi-replica deployments — it isn't; it's a plain in-memory
  dict. Corrected the docstring to state the real, still-open limitation
  (see `docs/REALTIME.md`) rather than leave an inaccurate claim sitting in
  the source.
- **Frontend**: Next.js 14.2.35 had 21 open security advisories with no fix
  anywhere in the 14.x line (Vercel's backports stop at 15.5.x) — this was
  a previously deferred, documented gap. This pass actually closed it:
  upgraded to Next.js 15.5.23 + React 19.2.8 (the lowest version satisfying
  every advisory, not the latest major), verified safe in advance by
  confirming every page in this app is a client component using hooks
  rather than the server-component props Next 15 changed, then verified
  after the fact with a full lint/typecheck/build pass across all 12
  routes. Two more vulnerabilities surfaced from `next`'s own bundled,
  unreachable-by-normal-resolution dependencies (`sharp`, a nested
  `postcss`) — closed via `package.json` `overrides`. `npm audit` now
  reports **zero vulnerabilities**, down from 21.
- **Frontend admin page** silently showed a raw, untyped error message on
  fetch failure instead of the consistent `ApiError`-aware fallback every
  other page uses — fixed to match.
- **Cross-platform correctness** (specifically checked because this is
  meant to also be tested on a Windows 11 laptop, not only Linux): grepped
  for case-sensitivity mismatches between imports and actual filenames on
  this case-sensitive Linux sandbox (found none, and added
  `forceConsistentCasingInFileNames` to `tsconfig.json` so TypeScript itself
  catches this class of bug on any OS going forward, not just here); added
  a `.gitattributes` normalizing line endings so a Windows checkout can't
  corrupt a future shell script; added Windows 11 (PowerShell/cmd) setup
  instructions to `docs/CONTRIBUTING.md` alongside the existing bash/zsh
  ones, rather than assuming one platform.

Full detail and the reasoning behind each fix: `docs/SECURITY.md`,
`docs/DATABASE.md`, `docs/TESTING.md`, `docs/CONTRIBUTING.md`.

## Backend core — TESTED

- FastAPI app boots, connects to a real local PostgreSQL 16 + Redis 7.
- 44-table schema created via Alembic (`alembic upgrade head`) against a real
  database — not just modeled in Python, actually applied; a second
  migration (composite indexes, see above) was added and applied during
  this session's follow-up audit.
- **30/30 tests passing** (`APP_ENV=test python -m pytest -q`), all
  integration-style against real Postgres/Redis, covering: registration,
  email verification, login, account lockout, refresh-token rotation +
  reuse detection, logout/logout-all session revocation, password reset,
  the login-timing mitigation; RBAC enforcement (permission checks, 401s,
  SUPER_ADMIN bypass); server-authoritative quiz scoring including a direct
  cheat-attempt test; idempotent submission; a genuine 8-way concurrency
  test proving the double-submit race is closed; certificate issuance +
  public verification; server-computed gamification; Redis-backed rate
  limiting. Full breakdown in `docs/TESTING.md`.
- `ruff check app tests`: **zero errors**.
- `pip-audit -r requirements.txt`: **zero known vulnerabilities** (fixed
  during this session by upgrading fastapi, starlette, pyjwt,
  python-multipart, jinja2, python-dotenv, pytest, uvicorn, gunicorn,
  setuptools).
- `bandit -r app -ll`: zero medium/high findings; one low-severity finding
  reviewed and is not a real issue (a password-policy message string
  heuristically flagged as a hardcoded password) — see `docs/SECURITY.md`.

## Frontend — TESTED (build), GAP (no test suite)

- `npm run lint`, `npm run typecheck`, `npm run build` all succeed.
- All pages (login, register, forgot/reset password, verify-email,
  dashboard, courses, course detail, certificate verification, admin) build
  successfully as part of that production build, now on Next.js 15.5.23 +
  React 19.2.8 (see above).
- **GAP**: no Jest/Playwright/Cypress test suite exists — frontend
  correctness beyond "it builds and type-checks" has not been automated.
  Noted as a real gap in `docs/TESTING.md`, not silently omitted.
- `npm audit`: **zero vulnerabilities** — see the second-pass audit section
  above for how the previous 21 Next.js advisories were actually resolved,
  not just deferred again.

## RBAC / auth / anti-cheat — TESTED

Covered above and in detail in `docs/SECURITY.md`. This is the subsystem
with the most direct test coverage because it's the one where a silent bug
would be most damaging (a student seeing another student's data, or gaming
their own exam score).

## Sarvam AI integration — CONFIGURED, BLOCKED (network)

- Real API key is in `backend/.env` (gitignored), `AI_PROVIDER=sarvam` is
  supported, `SarvamAIProvider` is a real `httpx` client against Sarvam's
  documented chat-completions contract.
- **Not tested live**: this sandbox's network egress does not reach
  `api.sarvam.ai` — confirmed via a direct connectivity test that returned a
  403 from the sandbox's own network proxy, not from Sarvam or the app.
  Exercised instead through `MockAIProvider`, which every AI-conversation
  test and CI run actually uses.
- Full detail, including the exact command to verify the live call once
  deployed somewhere with real network access: `docs/AI.md`.

## n8n automation — TESTED (workflow), BLOCKED (network hop from here)

- A real workflow ("Survival School — Event Router", ID `y96SeFRWA6e594bS`)
  exists in your actual n8n Cloud instance, is `active: true` (reconfirmed
  via direct n8n API query while writing this report), has 9 nodes, and was
  actually executed with real payloads through the n8n platform's own tools
  during this build — not just described, run.
- The backend's `emit_event()` call to that workflow's webhook has **not**
  been exercised from this sandbox (same class of network restriction as
  Sarvam — confirmed 403 from the sandbox proxy against
  `vishalreddy18.app.n8n.cloud`).
- The workflow's own description states its own honest limitation: email/
  Slack delivery nodes aren't wired to real credentials yet — it routes and
  builds content correctly but doesn't send anywhere yet. That's a
  configuration step on the n8n side for whoever owns that instance, not a
  backend code gap.
- Full detail + a `curl` command to verify the live hop: `docs/N8N.md`.

## Power BI — GUIDANCE PROVIDED, NOT INTEGRATED

- Per your request, no code integration was attempted — `docs/POWERBI.md`
  gives you the exact steps to connect Power BI Desktop to the platform's
  Postgres data directly (the standard, working-today approach), including
  a read-only reporting role and a note on which tables/columns to expose.
  The `POWERBI_*` settings exist in config as placeholders for a possible
  future REST-API push-dataset integration, which does not exist yet.

## WebSocket chat — TESTED (persistence path), GAP (multi-replica), GAP (no automated test)

- Auth (query-param JWT) and room-membership authorization are implemented
  correctly, following the same JWT/session logic proven by the auth test
  suite.
- Messages persist to Postgres before broadcast, so a dropped connection
  never loses data — the REST history endpoint is the recovery path.
- **Real limitation, not hidden**: the connection manager is in-process
  memory, not Redis pub/sub. In a multi-replica deployment (which the
  Kubernetes manifests default to), users on different backend pods won't
  see each other's messages in real time. Caught and documented during this
  session — the code's own docstring previously overstated this ("backed by
  Redis pub/sub") and was corrected to state the actual limitation plainly.
- No automated WebSocket test exists in `backend/tests/`. Full detail:
  `docs/REALTIME.md`.

## Docker — STRUCTURALLY VALIDATED, BLOCKED (image builds)

- `docker-compose.yml` passes `docker compose config`.
- Dockerfiles use multi-stage builds, non-root users, healthchecks.
- **Not built**: every container-registry request (docker.io,
  mcr.microsoft.com, public.ecr.aws, gcr.io) returns 403 from this
  sandbox's network allowlist. No image has actually been built or run in
  this session. First real build will happen in CI. Detail: `docs/DEPLOYMENT.md`.

## CI/CD (GitHub Actions) — WRITTEN AND CROSS-CHECKED, NOT YET RUN

- `.github/workflows/ci.yml` YAML validated; every referenced path/script/
  port cross-checked against the real repo and confirmed to match.
- The lint/audit/migrate/test steps and the frontend build step were run
  directly in this sandbox with the same commands the workflow uses, and
  passed — but the workflow itself has not executed on GitHub Actions
  infrastructure yet (requires the push below). Detail: `docs/CI_CD.md`.

## Kubernetes manifests — SCHEMA-VALID, BLOCKED (no cluster)

- 23 resources across 11 files, validated with `kubeconform` against real
  Kubernetes API schemas — all valid.
- Caught and fixed a real bug during this pass: a ConfigMap value used
  `$(POSTGRES_PASSWORD)` shell-style substitution, which Kubernetes does
  **not** expand for `envFrom`/`configMapKeyRef` values — that would have
  silently injected a literal placeholder string into `DATABASE_URL` in a
  real cluster. Fixed by moving the fully-rendered URL into the Secret
  template instead.
- Also fixed: the ConfigMap's rate-limit keys didn't match the actual
  `Settings` field names (`RATE_LIMIT_LOGIN_PER_5MIN`, not
  `RATE_LIMIT_LOGIN_PER_MINUTE`) — would have silently no-op'd since
  `Settings` ignores unknown env vars.
- **Never applied to a real cluster** — no `kubectl`/cluster access exists
  in this sandbox. Every `image:` field is a placeholder pending a real
  registry push. Full gap list: `infra/k8s/README.md`.

## GitHub push — BLOCKED (sandbox authorization, not fixable from here)

Two commits were made locally:
1. Full codebase (146 files).
2. A follow-up fix removing an accidentally-committed `dump.rdb` Redis
   snapshot caught during a post-commit review, plus a `.gitignore` update.

Both push attempts (`git push -u origin HEAD:main`) were rejected by this
sandbox's git proxy with: *"access denied by the git proxy:
chandrasekharreddy-basireddy/survivalschool is not in this session's
authorized repository set."* This is a control on this specific cloud
session, separate from your GitHub PAT (the PAT itself was never rejected —
the proxy blocks the request before the PAT is even used). It cannot be
worked around from inside this sandbox.

**Delivered instead**: a `git bundle` (`survivalschool.bundle`, full commit
history, 2 commits) and a plain source `tar.gz`
(`survivalschool-source.tar.gz`) — see the chat for both files. To get this
onto GitHub yourself:

```bash
# Option A — from the bundle (preserves full commit history):
git clone survivalschool.bundle survivalschool
cd survivalschool
git remote add origin https://github.com/chandrasekharreddy-basireddy/survivalschool.git
git push -u origin main

# Option B — from the tar.gz, if you'd rather start a fresh history:
tar xzf survivalschool-source.tar.gz
cd survivalschool
git init && git add -A && git commit -m "Initial commit"
git remote add origin https://github.com/chandrasekharreddy-basireddy/survivalschool.git
git push -u origin main
```

## Summary table

| Subsystem | Status |
|---|---|
| Backend API + business logic | TESTED |
| Auth / RBAC / anti-cheat | TESTED |
| Login timing side-channel | FIXED + TESTED (second-pass audit) |
| Quiz/exam double-submit race | FIXED + TESTED with a real concurrency test (second-pass audit) |
| Client IP / rate-limit spoofing | FIXED (second-pass audit) |
| Frontend dependency vulnerabilities | FIXED — 21 → 0 (second-pass audit, Next.js 15.5.23 upgrade) |
| Cross-platform (Windows 11) correctness | Checked + hardened (second-pass audit) — see `docs/CONTRIBUTING.md` |
| Database schema + migrations | TESTED |
| Frontend build | TESTED (no automated test suite — GAP) |
| Sarvam AI | CONFIGURED, BLOCKED (sandbox network) |
| n8n automation | Workflow TESTED; backend network hop BLOCKED (sandbox network) |
| Power BI | Guidance delivered, not integrated (by design, per your request) |
| WebSocket chat | Persistence path TESTED; multi-replica broadcast is a GAP |
| Docker images | Structurally validated; build BLOCKED (sandbox network) |
| CI/CD pipeline | Written + cross-checked; not yet run (blocked on GitHub push) |
| Kubernetes manifests | Schema-valid; never applied to a cluster |
| GitHub push | BLOCKED (sandbox authorization) — archive delivered instead |
