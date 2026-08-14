# Observability

## Structured logging

`app/core/logging.py` configures `structlog` to emit JSON to stdout, with
ISO timestamps, log level, and (on exceptions) full stack info. Every log
line is machine-parseable — no printf-style logging in the request path.

## Request tracing

`RequestContextMiddleware` (`app/core/middleware.py`) generates or propagates
an `x-request-id` header on every request, logs a structured `request` event
with method/path/status/duration for every request, and echoes the ID back
in the response header so a client-reported issue can be correlated to a
specific server-side log line. The same request ID is threaded into audit
log entries (`services/audit_service.py`) for admin-facing actions.

## Health endpoints

Three tiers, matching Kubernetes probe conventions (see `infra/k8s/06-backend.yaml`):

- `GET /api/v1/live` — process is up, no dependency checks (liveness probe).
- `GET /api/v1/ready` — checks real DB connectivity via `check_db_health()`,
  returns 503 if the database is unreachable (readiness probe — a pod that
  fails this is pulled from the Service's endpoint list without being killed).
- `GET /api/v1/health` — general summary, useful for manual/dashboard checks.
- `GET /api/v1/admin/system-health` (authenticated, `system.manage`) —
  reports configuration status of DB, Redis, n8n, and Sarvam AI, so an admin
  can see at a glance which external integrations are actually wired up in a
  given environment.

## Security headers on every response

`SecurityHeadersMiddleware` adds `X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, and
(when served over HTTPS) `Strict-Transport-Security` — verifiable by curling
any endpoint and inspecting response headers.

## Audit logging

`services/audit_service.py` writes to the `audit_logs` table for
administrative/sensitive actions (role grants, course deletion, etc.),
capturing actor, action, target, and the request ID. Exposed to admins via
`GET /api/v1/admin/audit-logs`.

## Error tracking (Sentry) — real integration, inert by default

Both the backend and frontend are wired for Sentry, but neither ships a
real DSN — this repo has no Sentry account, and fabricating a DSN would
mean shipping fake credentials, which violates this project's "no fake
data" standard. Instead, the integration is genuinely functional and
becomes active the moment a real DSN is set; until then it's a documented,
verified no-op, not a stub.

**Backend** (`app/main.py`, `app/config.py`): `sentry_sdk.init()` is only
called `if settings.SENTRY_DSN` — unset by default (`SENTRY_DSN=` in
`.env.example`). `app/core/exceptions.py`'s `unhandled_exception_handler`
now does two things for every genuinely unhandled exception (not an
`AppError` a route raised on purpose): logs it via `structlog` with a full
traceback (this was a real gap closed in this pass — unhandled 500s
previously weren't logged anywhere), and calls `sentry_sdk.capture_exception()`,
which is a documented safe no-op when `init()` was never called. Verified
in this build: the app boots identically with `SENTRY_DSN` unset (default)
and with a well-formed placeholder DSN set (`sentry_sdk.Hub.current.client`
confirmed non-`None`, matching the configured DSN) — both via direct
Python import and the full `pytest` suite (92/92 passing with the SDK
installed).

**Frontend** (`src/instrumentation.ts`, `src/instrumentation-client.ts`,
`src/sentry.server.config.ts`, `src/sentry.edge.config.ts`,
`src/app/global-error.tsx`, `next.config.mjs`): standard Next.js 15 App
Router Sentry setup (`@sentry/nextjs` v10), each config file guarded by
`if (process.env.NEXT_PUBLIC_SENTRY_DSN)`. A DSN is not a secret — it's
designed to be embedded in a public client bundle, so `NEXT_PUBLIC_`
exposure here is intentional, not a leak; write access to a Sentry project
is controlled separately by server-side auth tokens (`SENTRY_AUTH_TOKEN`,
also unset by default). `global-error.tsx` reports root-layout errors that
nothing else in the tree can catch. Verified in this build: `npm run build`
succeeds cleanly with `NEXT_PUBLIC_SENTRY_DSN` unset (default, all 39
routes build) and with a well-formed placeholder DSN set (exercising the
actual client-init code path) — both produce a clean production build with
zero errors or warnings.

To turn this on for real: create a Sentry project, set `SENTRY_DSN` (backend)
and `NEXT_PUBLIC_SENTRY_DSN` (frontend) to its DSN, and optionally
`SENTRY_ORG`/`SENTRY_PROJECT`/`SENTRY_AUTH_TOKEN` (frontend) to enable
source map upload during `next build`. Nothing else needs to change.

## What is NOT set up

- **No log aggregation/shipping is configured** — logs go to stdout, which is
  correct for container orchestration (the platform, e.g. CloudWatch Logs,
  GCP Logging, or a Fluent Bit sidecar in Kubernetes, is expected to collect
  them), but no such collector is part of this repository.
- **No distributed tracing** (e.g. OpenTelemetry spans across
  backend → n8n → Sarvam) — the request ID gives correlation within a single
  service's logs, not a cross-service trace.
- **No alerting rules** are defined anywhere in this repository — alerting
  policy is inherently specific to whatever monitoring stack a real
  deployment target uses.
