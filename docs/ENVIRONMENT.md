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
| `RUN_INPROCESS_SCHEDULER` | `true` | Runs the weekend-exam/contest scheduler inside the web process — needed when no standalone worker is deployed. A Redis leader lock keeps multiple gunicorn workers from double-ticking; disabled automatically under `APP_ENV=test`. |

## Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...localhost.../survivalschool` | Async driver, used at runtime |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://...localhost.../survivalschool` | Sync driver, used by Alembic only |
| `DB_POOL_SIZE` | `5` | Deliberately small — see the comment on this field in `config.py`. A 2-worker deploy with the old 10+20 defaults could try to open 60 connections against Supabase's session-mode pooler, which caps at 15 total; load testing reproduced exactly that (`EMAXCONNSESSION`, every request past the cap 500'd). |
| `DB_MAX_OVERFLOW` | `2` | 5+2=7 per worker keeps a 2-worker deploy at 14 total, under the pooler's cap. Raise only alongside a matching increase to the pooler's own connection limit. |

## Redis

| Variable | Default |
|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` |

## Auth / JWT

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET` | `""` (empty) | **Not auto-generated per boot** — a per-boot random secret would silently invalidate every issued access token on each restart. Empty in `development`/`test` falls back to a fixed, obviously-non-secret dev placeholder so restarting the dev server doesn't log everyone out; empty in `staging`/`production` raises a startup error instead. Must be explicitly set and ≥32 chars in production — `validate_for_production()` enforces this. |
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

Configurable so environments (and the test suite, which legitimately calls
these endpoints far more often than any real client would in the same
window) can tune them without code changes.

| Variable | Default | Notes |
|---|---|---|
| `RATE_LIMIT_REGISTER_PER_HOUR` | `5` | |
| `RATE_LIMIT_LOGIN_PER_5MIN` | `10` | |
| `RATE_LIMIT_RESEND_VERIFY_PER_HOUR` | `3` | Per-email. |
| `RATE_LIMIT_RESEND_VERIFY_PER_HOUR_PER_IP` | `10` | Per-IP companion — the per-email limit alone doesn't stop one attacker email-bombing many different victims. |
| `RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR` | `3` | Per-email. |
| `RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR_PER_IP` | `10` | Per-IP companion, same reasoning as resend-verify above. |
| `RATE_LIMIT_TOKEN_ENDPOINT_PER_HOUR_PER_IP` | `30` | Guards `verify-email`/`reset-password`; defense-in-depth since both take an unguessable 48-byte token, not an email. |
| `RATE_LIMIT_EXAM_START_PER_HOUR` | `10` | |
| `RATE_LIMIT_2FA_VERIFY_PER_5MIN` | `10` | Guards 2FA setup-confirmation and 2FA-disable's password re-check — a hijacked session shouldn't brute-force either with no throttle. |
| `RATE_LIMIT_AI_WEEKLY_REGISTER_PER_HOUR` | `5` | |
| `RATE_LIMIT_FOLLOW_REQUEST_PER_HOUR` | `30` | Per-requester — bounds how many distinct people one account can spam with follow requests. |
| `RATE_LIMIT_PEOPLE_SEARCH_PER_MINUTE` | `30` | |

## Certificates

| Variable | Default | Notes |
|---|---|---|
| `CERTIFICATE_VALIDITY_DAYS` | unset (never expires) | Set an integer (e.g. `730`) for time-limited certifications. |

## CORS

| Variable | Default | Notes |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list, parsed by `Settings.cors_origins_list` |

## Email

| Variable | Default | Notes |
|---|---|---|
| `EMAIL_BACKEND` | `console` | One of `console`, `smtp`, `resend`, `brevo`. `console` prints to stdout (dev only — disallowed in production). `smtp` does **not** work on Render (outbound SMTP ports are blocked at the network layer); use `brevo` or `resend` there instead, both over HTTPS. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | unset / `587` / unset / unset | Required if `EMAIL_BACKEND=smtp`. |
| `RESEND_API_KEY` | unset | Required if `EMAIL_BACKEND=resend` (starts with `re_`). `EMAIL_FROM` must be on a domain verified in Resend. |
| `BREVO_API_KEY` | unset | Required if `EMAIL_BACKEND=brevo` (starts with `xkeysib-`). Only needs `EMAIL_FROM` verified as a single sender in Brevo — no domain DNS required. |
| `EMAIL_FROM` | `Survival School <no-reply@survivalschool.dev>` | |
| `FRONTEND_URL` | `http://localhost:3000` | Used to build verification/reset/certificate links |

## AI (Sarvam)

| Variable | Default | Notes |
|---|---|---|
| `AI_PROVIDER` | `mock` | `mock` or `sarvam` — see `docs/AI.md` |
| `SARVAM_API_KEY` | unset | Required if `AI_PROVIDER=sarvam` (enforced at production startup) |
| `SARVAM_BASE_URL` | `https://api.sarvam.ai` | |
| `SARVAM_CHAT_MODEL` | `sarvam-105b` | `sarvam-m` (24B) was deprecated and removed from Sarvam's Chat Completions API — sending it now returns 400 Bad Request. `sarvam-105b` is the current flagship chat model. |
| `SARVAM_VISION_MODEL` | `gemma4` | Used only for image-input AI tutor messages, via the newer (still-beta) `/v2/chat/completions` endpoint — `sarvam-105b` on `/v1` has no documented vision support. |
| `AI_DAILY_MESSAGE_LIMIT` | `100` | Per user, per day |
| `AI_REQUEST_TIMEOUT_SECONDS` | `30` | |

**Known live reliability issue (confirmed in production):** Sarvam intermittently
returns a 2xx response with completely empty message content for an
otherwise-ordinary request. `ai_provider.py` retries this automatically
(`_EMPTY_RESPONSE_RETRY_ATTEMPTS`), but the failure can persist across every
retry for a given request, in which case question generation for that
topic/contest genuinely fails — not a bug in this app's request shape, an
upstream Sarvam issue. `elimination_service.py::start_battle` surfaces this
honestly once it's had long enough to be sure generation isn't just still
running (see that function's comment).

## n8n

| Variable | Default | Notes |
|---|---|---|
| `N8N_WEBHOOK_BASE_URL` | unset | If unset, `emit_event()` no-ops — see `docs/N8N.md` |
| `N8N_WEBHOOK_SECRET` | random 32-byte, generated at import if unset | Sent as `x-n8n-webhook-secret` header |

## Power BI

| Variable | Default | Notes |
|---|---|---|
| `POWERBI_TENANT_ID` / `POWERBI_CLIENT_ID` / `POWERBI_CLIENT_SECRET` / `POWERBI_WORKSPACE_ID` | all unset | **Implemented** — `app/services/powerbi_service.py` and wired into the admin sync endpoint/worker job; see `docs/POWERBI.md`. Leave unset to disable the sync. |

## Storage

| Variable | Default | Notes |
|---|---|---|
| `STORAGE_BACKEND` | `local` | `local` or `supabase` — both implemented, see `app/services/storage_service.py`. Render's own container disk is ephemeral (wiped on every redeploy), so `local` is fine for dev/CI but not for real user-uploaded files in production; use `supabase` there for durable storage. |
| `STORAGE_LOCAL_PATH` | `var/uploads` | Relative to the app's working directory by default (a Render web service usually can't create top-level dirs like `/data/uploads`). Deployments that mount a real persistent disk should set this explicitly. Only used when `STORAGE_BACKEND=local`. |
| `SUPABASE_STORAGE_URL` | unset | e.g. `https://<ref>.supabase.co`. Required if `STORAGE_BACKEND=supabase`. |
| `SUPABASE_STORAGE_BUCKET` | `survivalschool-uploads` | |
| `SUPABASE_SERVICE_ROLE_KEY` | unset | Secret, bypasses RLS — the backend already enforces its own auth/visibility checks before touching storage. Required if `STORAGE_BACKEND=supabase`. |
| `MAX_UPLOAD_MB` | `25` | |

## Destructive maintenance operations

| Variable | Default | Notes |
|---|---|---|
| `MAINTENANCE_SECRET` | unset | When set, `POST /api/v1/admin/maintenance/reset-accounts` is enabled and requires this exact value in the `X-Maintenance-Secret` header. Exists because some hosts (Render's free tier) don't always offer easy interactive shell access — meant to be unset again immediately after use. |

## Observability

| Variable | Default | Notes |
|---|---|---|
| `LOG_LEVEL` | `INFO` | |
| `SERVICE_VERSION` | `1.0.0` | |
| `SENTRY_DSN` | unset | If unset, `sentry_sdk.init()` is never called — zero overhead, zero fabricated DSN. See `docs/OBSERVABILITY.md`. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | |

## WebAuthn / Passkeys

| Variable | Default | Notes |
|---|---|---|
| `WEBAUTHN_RP_ID` | `localhost` | **Must** be set to the real production domain (e.g. `survivalschool.vercel.app`, no scheme/port) or every passkey registration/assertion fails origin verification — a passkey is permanently scoped by the browser to the RP ID it was registered against. |
| `WEBAUTHN_RP_NAME` | `Survival School` | Display name shown in the browser's passkey UI. |
| `WEBAUTHN_ORIGIN` | `http://localhost:3000` | Must match the frontend's real production origin exactly (scheme + host + port). |

## Web Push (VAPID)

| Variable | Default | Notes |
|---|---|---|
| `VAPID_PUBLIC_KEY` | unset | Generate a real per-deployment keypair with `backend/scripts/generate_vapid_keys.py`. Push sending silently no-ops if unset. See `docs/PUSH_NOTIFICATIONS.md`. |
| `VAPID_PRIVATE_KEY` | unset | Never commit — this is a real secret, exactly like `JWT_SECRET`. |
| `VAPID_SUBJECT` | `mailto:admin@example.com` | Contact URI sent in the VAPID JWT `sub` claim; set to a real one in production. |

## Frontend (`frontend/.env.local` or build args)

| Variable | Notes |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Baked in at build time (see `docs/DEPLOYMENT.md`), e.g. `http://localhost:8000/api/v1` |
| `NEXT_PUBLIC_WS_BASE_URL` | Baked in at build time, e.g. `ws://localhost:8000` |
| `NEXT_PUBLIC_SITE_URL` | Canonical public site origin, e.g. `https://survivalschool.vercel.app`. Used by `sitemap.ts` and the root layout's `metadataBase`. Falls back to `https://survivalschool.vercel.app` if unset — set it explicitly if the deployment's real domain ever changes. |
