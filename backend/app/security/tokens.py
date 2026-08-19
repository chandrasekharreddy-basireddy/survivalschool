"""JWT access tokens + opaque refresh/verification/reset tokens.

Refresh tokens, email verification tokens, and password reset tokens are
generated as high-entropy random strings and only their SHA-256 hash is ever
persisted (spec section 6 & 8) — the raw value exists only in the outbound
email/response and is never recoverable from the database.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

settings = get_settings()


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(user_id: uuid.UUID, roles: list[str], session_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "roles": roles,
        "sid": str(session_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def create_mfa_pending_token(user_id: uuid.UUID) -> str:
    """A distinct, short-lived, narrowly-scoped JWT issued after a correct
    password but before a required TOTP code — proves "this request already
    passed password auth" without granting API access. Its "type" claim is
    "mfa_pending", never "access", so get_current_user's `type != "access"`
    check (dependencies.py) rejects it outright if anyone tries to use it as
    a bearer token anywhere else — the same token-type-confusion defense
    already used for the access/refresh split."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "mfa_pending",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_mfa_pending_token(token: str) -> dict:
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "mfa_pending":
        raise jwt.InvalidTokenError("Not an MFA-pending token.")
    return payload


def new_refresh_token_pair() -> tuple[str, str, datetime]:
    """Returns (raw_token, token_hash, expires_at). Only token_hash is stored."""
    raw = generate_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)
    return raw, hash_token(raw), expires_at


def new_email_verification_token() -> tuple[str, str, datetime]:
    raw = generate_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS)
    return raw, hash_token(raw), expires_at


def new_password_reset_token() -> tuple[str, str, datetime]:
    raw = generate_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES)
    return raw, hash_token(raw), expires_at
