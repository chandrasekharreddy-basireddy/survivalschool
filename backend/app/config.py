"""
Centralized, fail-fast application configuration.

Every mandatory production setting is validated at import time. Missing
required config raises immediately rather than letting the app boot into a
broken state (spec section 42: "Fail fast for missing mandatory production
configuration").
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Fixed, non-secret placeholder used only when APP_ENV is development/test.
# validate_for_production() rejects it, so it can never reach production.
DEV_JWT_SECRET = "insecure-development-only-jwt-secret-do-not-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_NAME: str = "Survival School"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://survivalschool:survivalschool@localhost:5432/survivalschool"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://survivalschool:survivalschool@localhost:5432/survivalschool"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Auth / JWT ---
    # Deliberately NOT default_factory=secrets.token_urlsafe: a per-boot random
    # secret silently invalidates every issued access token and breaks refresh
    # rotation on each restart, producing intermittent mass logouts that are
    # extremely hard to diagnose. Unset is an error everywhere except local
    # dev/test, which fall back to a *fixed* (and obviously non-secret) value so
    # that restarting the dev server does not log everyone out.
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 30
    EMAIL_VERIFICATION_TTL_HOURS: int = 24
    PASSWORD_RESET_TTL_MINUTES: int = 30
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCK_MINUTES: int = 15

    # --- Client IP resolution ---
    # X-Forwarded-For is a client-supplied header — trusting it unconditionally
    # lets any direct caller set an arbitrary value, which would let an
    # attacker get a fresh rate-limit bucket per request (defeating login/
    # register brute-force throttling) and poison the IP address recorded in
    # audit logs and session records. Only trust it when this deployment is
    # actually known to sit behind a reverse proxy that sets/overwrites this
    # header correctly (nginx-ingress, an ALB, Cloudflare, etc.) — the default
    # is off, so a misconfigured or missing proxy fails safe to the raw TCP
    # peer address rather than failing open to a spoofable header.
    TRUST_PROXY_HEADERS: bool = False

    # --- Rate limits (spec section 49) — configurable so environments (and
    # the test suite, which legitimately calls these endpoints far more often
    # than any real client would in the same window) can tune them without
    # code changes. ---
    RATE_LIMIT_REGISTER_PER_HOUR: int = 5
    RATE_LIMIT_LOGIN_PER_5MIN: int = 10
    RATE_LIMIT_RESEND_VERIFY_PER_HOUR: int = 3
    RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR: int = 3
    RATE_LIMIT_EXAM_START_PER_HOUR: int = 10

    # --- Certificates ---
    # Days a certificate remains valid after issuance; None (default) means
    # certificates never expire. Set to an integer (e.g. 730 for 2 years) for
    # time-limited certifications (spec section 8: "Expiry date (optional)").
    CERTIFICATE_VALIDITY_DAYS: int | None = None

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- Email ---
    # On Render, use "brevo" (no domain needed -- just a verified sender email)
    # or "resend" (needs a verified domain). Both send over HTTPS. The "smtp"
    # backend does NOT work on Render: Render blocks outbound SMTP ports
    # (25/465/587) at the network layer, so smtplib fails there with
    # "[Errno 101] Network is unreachable" regardless of credentials. "smtp"
    # is still valid on hosts that permit SMTP egress.
    EMAIL_BACKEND: Literal["console", "smtp", "resend", "brevo"] = "console"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    # Resend HTTPS API key (starts with "re_"). Required when EMAIL_BACKEND=
    # resend. EMAIL_FROM must be on a domain verified in Resend.
    RESEND_API_KEY: str | None = None
    # Brevo HTTPS API key (starts with "xkeysib-"). Required when
    # EMAIL_BACKEND=brevo. Only needs the EMAIL_FROM address verified as a
    # single sender in Brevo -- no domain DNS required.
    BREVO_API_KEY: str | None = None
    EMAIL_FROM: str = "Survival School <no-reply@survivalschool.dev>"
    FRONTEND_URL: str = "http://localhost:3000"

    # --- AI (Sarvam) ---
    AI_PROVIDER: Literal["mock", "sarvam"] = "mock"
    SARVAM_API_KEY: str | None = None
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"
    # sarvam-m (24B) was deprecated and removed from Sarvam's Chat Completions
    # API -- sending it returns 400 Bad Request. sarvam-105b is the current
    # flagship chat model. See https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview
    SARVAM_CHAT_MODEL: str = "sarvam-105b"
    AI_DAILY_MESSAGE_LIMIT: int = 100
    AI_REQUEST_TIMEOUT_SECONDS: int = 30

    # --- n8n ---
    N8N_WEBHOOK_BASE_URL: str | None = None
    N8N_WEBHOOK_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    # --- Power BI ---
    POWERBI_TENANT_ID: str | None = None
    POWERBI_CLIENT_ID: str | None = None
    POWERBI_CLIENT_SECRET: str | None = None
    POWERBI_WORKSPACE_ID: str | None = None

    # --- File storage ---
    STORAGE_BACKEND: Literal["local", "supabase"] = "local"
    # Default to a path under the app's own working directory rather than an
    # absolute root path like "/data/uploads" -- the app process (in CI, in
    # Docker, and on Render's non-root web service containers) usually can't
    # create top-level directories and hits PermissionError: [Errno 13] on
    # the first upload. Deployments that mount a real persistent disk (e.g. a
    # Render Disk at /data) should set STORAGE_LOCAL_PATH explicitly via env.
    # Only used when STORAGE_BACKEND=local -- Render's own container disk is
    # ephemeral (wiped on every redeploy), so "local" is fine for dev/CI but
    # not for real user-uploaded files in production; use STORAGE_BACKEND=
    # supabase there instead for durable storage.
    STORAGE_LOCAL_PATH: str = "var/uploads"
    # --- Supabase Storage (real backend for durable file uploads) ---
    SUPABASE_STORAGE_URL: str | None = None  # e.g. https://<ref>.supabase.co
    SUPABASE_STORAGE_BUCKET: str = "survivalschool-uploads"
    # Service role key (secret, bypasses RLS) -- the backend already enforces
    # its own auth/visibility checks in app/api/v1/files.py before touching
    # storage, so a service-role-authenticated bucket is the correct model
    # here rather than trying to map our own JWT users onto Supabase Auth.
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    MAX_UPLOAD_MB: int = 25

    # --- Destructive maintenance operations ---
    # Optional, unset by default (endpoint is 404-equivalent/inert unless
    # explicitly configured). When set, POST /api/v1/admin/maintenance/reset-accounts
    # is enabled and requires this exact value in the X-Maintenance-Secret
    # header. This exists because some real hosts (Render's free tier here)
    # don't always offer easy interactive shell access, so a one-time,
    # explicitly-gated HTTP escape hatch is the practical way to run a
    # real destructive maintenance script against production. Meant to be
    # unset again immediately after use.
    MAINTENANCE_SECRET: str | None = None

    # --- Observability ---
    LOG_LEVEL: str = "INFO"
    SERVICE_VERSION: str = "1.0.0"

    # --- Error tracking (Sentry) ---
    # Deliberately optional and inert by default: this build has no real
    # Sentry account/DSN to wire up, and fabricating one would violate the
    # "no fake credentials" rule for this project. SENTRY_DSN is None unless
    # a real deployment sets it via env var — see app/main.py for the guard
    # that skips sentry_sdk.init() entirely when it's unset, and
    # docs/OBSERVABILITY.md for what actually gets captured once it's set.
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    # --- Web Push (VAPID, RFC 8292) ---
    # Self-generated keypair — no Firebase/APNs/OneSignal account needed.
    # Generate a real pair per deployment with
    # `backend/scripts/generate_vapid_keys.py` and set these via env vars;
    # never commit real values (see backend/.env.example). Push sending is
    # a no-op (silently skipped) whenever these are unset, same inert-by-
    # default pattern as SENTRY_DSN above.
    VAPID_PUBLIC_KEY: str | None = None
    VAPID_PRIVATE_KEY: str | None = None
    VAPID_SUBJECT: str = "mailto:admin@example.com"

    @field_validator("APP_ENV")
    @classmethod
    def _validate_production_requirements(cls, v: str, info) -> str:
        return v

    @model_validator(mode="after")
    def _require_stable_jwt_secret(self) -> "Settings":
        if not self.JWT_SECRET:
            if self.APP_ENV in ("development", "test"):
                object.__setattr__(self, "JWT_SECRET", DEV_JWT_SECRET)
            else:
                raise ValueError(
                    "JWT_SECRET must be set explicitly when APP_ENV="
                    f"{self.APP_ENV!r}. Generate one with: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def validate_for_production(self) -> None:
        """Called explicitly at startup when APP_ENV=production. Fails fast."""
        missing = []
        if self.APP_ENV != "production":
            return
        if "localhost" in self.DATABASE_URL:
            missing.append("DATABASE_URL (points at localhost in production)")
        if self.EMAIL_BACKEND == "console":
            missing.append("EMAIL_BACKEND (console backend not allowed in production)")
        if self.EMAIL_BACKEND == "resend" and not self.RESEND_API_KEY:
            missing.append("RESEND_API_KEY (required when EMAIL_BACKEND=resend)")
        if self.EMAIL_BACKEND == "brevo" and not self.BREVO_API_KEY:
            missing.append("BREVO_API_KEY (required when EMAIL_BACKEND=brevo)")
        if self.EMAIL_BACKEND == "smtp" and not self.SMTP_HOST:
            missing.append("SMTP_HOST (required when EMAIL_BACKEND=smtp)")
        if self.AI_PROVIDER == "sarvam" and not self.SARVAM_API_KEY:
            missing.append("SARVAM_API_KEY")
        if self.STORAGE_BACKEND == "supabase" and not (self.SUPABASE_STORAGE_URL and self.SUPABASE_SERVICE_ROLE_KEY):
            missing.append("SUPABASE_STORAGE_URL/SUPABASE_SERVICE_ROLE_KEY (required when STORAGE_BACKEND=supabase)")
        if self.JWT_SECRET == DEV_JWT_SECRET:
            missing.append("JWT_SECRET (still set to the insecure development placeholder)")
        elif len(self.JWT_SECRET) < 32:
            missing.append("JWT_SECRET (too short)")
        if missing:
            raise RuntimeError(
                "Missing/invalid mandatory production configuration: " + ", ".join(missing)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
