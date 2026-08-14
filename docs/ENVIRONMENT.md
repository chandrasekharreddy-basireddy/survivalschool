# Environment variables

Source of truth: `backend/app/config.py::Settings` (Pydantic Settings — every
variable below is a real field there, not aspirational). `backend/.env.example`
mirrors this file and is the actual template to copy for local development.

## Core

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | One of `development`, `staging`, `production`, `test`. `production` triggers `validate_for_production()` fail-fast checks at startup. |
| `APP_NAME` | `Survival School` | |
| `API_V1_PREFIX` | `/api/v1` | |
| `DEBUG` | `false` | |

## Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...localhost.../survivalschool` | Async driver, used at runtime |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://...localhost.../survivalschool` | Sync driver, used by Alembic only |
| `DB_POOL_SIZE` | `10` | |
| `DB_MAX_OVERFLOW` | `20` | |

## Redis

| Variable | Default |
|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` |

## Auth / JWT

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET` | random 64-byte, generated at import if unset | **Must** be set explicitly and ≥32 chars in production — `validate_for_production()` enforces this |
| `JWT_REFRESH_SECRET` | random 64-byte, generated at import if unset | |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` | |
| `REFRESH_TOKEN_TTL_DAYS` | `30` | |
| `EMAIL_VERIFICATION_TTL_HOURS` | `24` | |
| `PASSWORD_RESET_TTL_MINUTES` | `30` | |
| `MAX_FAILED_LOGIN_ATTEMPTS` | `5` | |
| `ACCOUNT_LOCK_MINUTES` | `15` | |

## Client IP resolution

| Variable | Default | Notes |
|---|---|---|
| `TRUST_PROXY_HEADERS` | `false` | Set `true` only when this app sits behind a reverse proxy you know sets/overwrites `X-Forwarded-For` itself (the Kubernetes manifests do this — `infra/k8s/01-configmap.yaml` sets it `true` since that deployment always sits behind ingress-nginx). Leaving it `false` behind a real proxy means rate limiting and audit logs see the proxy's IP for every request, not each client's; leaving it `true` without a real proxy in front lets any caller spoof their IP. See `docs/SECURITY.md`. |

## Rate limits

| Variable | Default |
|---|---|
| `RATE_LIMIT_REGISTER_PER_HOUR` | `5` |
| `RATE_LIMIT_LOGIN_PER_5MIN` | `10` |
| `RATE_LIMIT_RESEND_VERIFY_PER_HOUR` | `3` |
| `RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR` | `3` |
| `RATE_LIMIT_EXAM_START_PER_HOUR` | `10` |

## CORS

| Variable | Default | Notes |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list, parsed by `Settings.cors_origins_list` |

## Email

| Variable | Default | Notes |
|---|---|---|
| `EMAIL_BACKEND` | `console` | `console` prints to stdout (dev only — `production` requires `smtp`) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | unset / `587` / unset / unset | Required if `EMAIL_BACKEND=smtp` |
| `EMAIL_FROM` | `Survival School <no-reply@survivalschool.dev>` | |
| `FRONTEND_URL` | `http://localhost:3000` | Used to build verification/reset/certificate links |

## AI (Sarvam)

| Variable | Default | Notes |
|---|---|---|
| `AI_PROVIDER` | `mock` | `mock` or `sarvam` — see `docs/AI.md` |
| `SARVAM_API_KEY` | unset | Required if `AI_PROVIDER=sarvam` (enforced at production startup) |
| `SARVAM_BASE_URL` | `https://api.sarvam.ai` | |
| `SARVAM_CHAT_MODEL` | `sarvam-m` | |
| `AI_DAILY_MESSAGE_LIMIT` | `100` | Per user, per day |
| `AI_REQUEST_TIMEOUT_SECONDS` | `30` | |

## n8n

| Variable | Default | Notes |
|---|---|---|
| `N8N_WEBHOOK_BASE_URL` | unset | If unset, `emit_event()` no-ops — see `docs/N8N.md` |
| `N8N_WEBHOOK_SECRET` | random 32-byte, generated at import if unset | Sent as `x-n8n-webhook-secret` header |

## Power BI

| Variable | Default | Notes |
|---|---|---|
| `POWERBI_TENANT_ID` / `POWERBI_CLIENT_ID` / `POWERBI_CLIENT_SECRET` / `POWERBI_WORKSPACE_ID` | all unset | Not used by any application code path yet — see `docs/POWERBI.md`; these fields exist in `Settings` so a future integration has somewhere to read credentials from, but nothing currently calls the Power BI API |

## Storage

| Variable | Default | Notes |
|---|---|---|
| `STORAGE_BACKEND` | `local` | `local` or `s3` — **only `local` is actually implemented**; see `docs/DEPLOYMENT.md` |
| `STORAGE_LOCAL_PATH` | `/data/uploads` | |
| `S3_BUCKET` / `S3_REGION` | unset | Reserved for a future S3 backend, not read by any code yet |
| `MAX_UPLOAD_MB` | `25` | |

## Observability

| Variable | Default |
|---|---|
| `LOG_LEVEL` | `INFO` |
| `SERVICE_VERSION` | `0.1.0` |

## Frontend (`frontend/.env.local` or build args)

| Variable | Notes |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Baked in at build time (see `docs/DEPLOYMENT.md`), e.g. `http://localhost:8000/api/v1` |
| `NEXT_PUBLIC_WS_BASE_URL` | Baked in at build time, e.g. `ws://localhost:8000` |
