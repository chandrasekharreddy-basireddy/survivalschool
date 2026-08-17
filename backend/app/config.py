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

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=200)

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Auth / JWT ---
    JWT_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    JWT_REFRESH_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = Field(default=15, ge=1, le=24 * 60)
    REFRESH_TOKEN_TTL_DAYS: int = Field(default=30, ge=1, le=365)
    EMAIL_VERIFICATION_TTL_HOURS: int = Field(default=24, ge=1, le=168)
    PASSWORD_RESET_TTL_MINUTES: int = Field(default=30, ge=5, le=1440)
    MAX_FAILED_LOGIN_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    ACCOUNT_LOCK_MINUTES: int = Field(default=15, ge=1, le=1440)

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
    RATE_LIMIT_REGISTER_PER_HOUR: int = Field(default=5, ge=1, le=10000)
    RATE_LIMIT_LOGIN_PER_5MIN: int = Field(default=10, ge=1, le=10000)
    RATE_LIMIT_RESEND_VERIFY_PER_HOUR: int = Field(default=3, ge=1, le=10000)
    RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR: int = Field(default=3, ge=1, le=10000)
    RATE_LIMIT_EXAM_START_PER_HOUR: int = Field(default=10, ge=1, le=10000)

    # --- Certificates ---
    # Days a certificate remains valid after issuance; None (default) means
    # certificates never expire. Set to an integer (e.g. 730 for 2 years) for
    # time-limited certifications (spec section 8: "Expiry date (optional)").
    CERTIFICATE_VALIDITY_DAYS: int | None = Field(default=None, ge=1, le=3650)

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
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
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
    AI_DAILY_MESSAGE_LIMIT: int = Field(default=100, ge=1, le=100000)
    AI_REQUEST_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=120)

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
    STORAGE_LOCAL_PATH: str = "var/uploads"
    SUPABASE_STORAGE_URL: str | None = None
    SUPABASE_STORAGE_BUCKET: str = "survivalschool-uploads"
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    MAX_UPLOAD_MB: int = Field(default=25, ge=1, le=1024)

    # --- Destructive maintenance operations ---
    MAINTENANCE_SECRET: str | None = None

    # --- Observability ---
    LOG_LEVEL: str = "INFO"
    SERVICE_VERSION: str = "1.0.0"

    # --- Error tracking (Sentry) ---
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.0, ge=0.0, le=1.0)

    # --- Web Push (VAPID, RFC 8292) ---
    VAPID_PUBLIC_KEY: str | None = None
    VAPID_PRIVATE_KEY: str | None = None
    VAPID_SUBJECT: str = "mailto:admin@example.com"

    @field_validator("APP_ENV")
    @classmethod
    def _validate_production_requirements(cls, v: str, info) -> str:
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def validate_for_production(self) -> None:
        """Called explicitly at startup when APP_ENV=production. Fails fast."""
        if self.APP_ENV != "production":
            return

        missing: list[str] = []
        explicit_fields = self.model_fields_set

        if "JWT_SECRET" not in explicit_fields:
            missing.append("JWT_SECRET (must be explicitly configured in production)")
        if "JWT_REFRESH_SECRET" not in explicit_fields:
            missing.append("JWT_REFRESH_SECRET (must be explicitly configured in production)")
        if len(self.JWT_SECRET) < 32:
            missing.append("JWT_SECRET (too short)")
        if len(self.JWT_REFRESH_SECRET) < 32:
            missing.append("JWT_REFRESH_SECRET (too short)")
        if self.JWT_SECRET == self.JWT_REFRESH_SECRET:
            missing.append("JWT_REFRESH_SECRET (must differ from JWT_SECRET)")
        if "localhost" in self.DATABASE_URL.lower():
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
        origins = self.cors_origins_list
        if not origins:
            missing.append("CORS_ORIGINS (must contain at least one trusted origin in production)")
        elif "*" in origins:
            missing.append("CORS_ORIGINS (wildcard origin is incompatible with credentialed requests)")
        elif all("localhost" in origin.lower() or "127.0.0.1" in origin for origin in origins):
            missing.append("CORS_ORIGINS (must not be localhost-only in production)")
        if "localhost" in self.FRONTEND_URL.lower() or "127.0.0.1" in self.FRONTEND_URL:
            missing.append("FRONTEND_URL (must not point at localhost in production)")
        if self.MAINTENANCE_SECRET is not None and len(self.MAINTENANCE_SECRET) < 32:
            missing.append("MAINTENANCE_SECRET (must be at least 32 characters when enabled)")
        if missing:
            raise RuntimeError(
                "Missing/invalid mandatory production configuration: " + ", ".join(missing)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
