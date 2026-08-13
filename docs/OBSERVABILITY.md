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

## What is NOT set up

- **No metrics exporter** (Prometheus/OpenTelemetry) is wired into the
  backend — `structlog` JSON logs are the only telemetry surface today.
  Adding a `/metrics` endpoint and instrumenting request latency histograms,
  DB pool saturation, and rate-limiter hit rates would be the natural next
  step for real production observability, and is not represented as done.
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
