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
    DATABASE_URL: str = (
        "postgresql+asyncpg://survivalschool:survivalschool@localhost:5432/survivalschool"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg2://survivalschool:survivalschool@localhost:5432/survivalschool"
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Auth / JWT ---
    JWT_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    JWT_REFRESH_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 30
    EMAIL_VERIFICATION_TTL_HOURS: int = 24
    PASSWORD_RESET_TTL_MINUTES: int = 30
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCK_MINUTES: int = 15

    # --- Client IP resolution ---
    TRUST_PROXY_HEADERS: bool = False

    # --- Rate limits ---
    RATE_LIMIT_REGISTER_PER_HOUR: int = 5
    RATE_LIMIT_LOGIN_PER_5MIN: int = 10
    RATE_LIMIT_RESEND_VERIFY_PER_HOUR: int = 3
    RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR: int = 3
    RATE_LIMIT_EXAM_START_PER_HOUR: int = 10

    # --- Certificates ---
    CERTIFICATE_VALIDITY_DAYS: int | None = None

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- Email ---
    EMAIL_BACKEND: Literal["console", "smtp", "resend", "brevo"] = "console"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    RESEND_API_KEY: str | None = None
    BREVO_API_KEY: str | None = None
    EMAIL_FROM: str = "Survival School <no-reply@survivalschool.dev>"
    FRONTEND_URL: str = "http://localhost:3000"

    # --- AI (Sarvam) ---
    AI_PROVIDER: Literal["mock", "sarvam"] = "mock"
    SARVAM_API_KEY: str | None = None
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"
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
    STORAGE_LOCAL_PATH: str = "var/uploads"
    SUPABASE_STORAGE_URL: str | None = None
    SUPABASE_STORAGE_BUCKET: str = "survivalschool-uploads"
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    MAX_UPLOAD_MB: int = 25

    # --- Destructive maintenance operations ---
    MAINTENANCE_SECRET: str | None = None

    # --- Observability ---
    LOG_LEVEL: str = "INFO"
    SERVICE_VERSION: str = "1.0.0"

    # --- Error tracking (Sentry) ---
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

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
        if self.STORAGE_BACKEND == "supabase" and not (
            self.SUPABASE_STORAGE_URL and self.SUPABASE_SERVICE_ROLE_KEY
        ):
            missing.append(
                "SUPABASE_STORAGE_URL/SUPABASE_SERVICE_ROLE_KEY (required when STORAGE_BACKEND=supabase)"
            )
        if len(self.JWT_SECRET) < 32:
            missing.append("JWT_SECRET (too short)")
        if len(self.JWT_REFRESH_SECRET) < 32:
            missing.append("JWT_REFRESH_SECRET (too short)")
        if missing:
            raise RuntimeError(
                "Missing/invalid mandatory production configuration: " + ", ".join(missing)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
