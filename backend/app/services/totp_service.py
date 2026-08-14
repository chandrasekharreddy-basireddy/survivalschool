"""Real TOTP (RFC 6238) two-factor authentication — the same algorithm
Google Authenticator, Authy, 1Password, etc. all implement. Deliberately
NOT SMS-based: SMS 2FA requires a paid third-party account (Twilio or
similar) this deployment doesn't have credentials for, and SMS OTP is
weaker anyway (SIM-swap risk) — TOTP needs nothing but an authenticator
app the user already has, so it's both more real and more secure to ship
here.

Secrets and backup codes:
- `User.totp_secret` holds the raw base32 TOTP secret. It is written on
  POST /auth/2fa/setup (pending, not yet enabled) and only takes effect
  once POST /auth/2fa/confirm proves the user's authenticator app actually
  has it (by producing a valid code) — this prevents a user from getting
  locked out by a secret their app never actually saved.
- `User.totp_backup_codes` stores only SHA-256 hashes of one-time backup
  codes (via security.tokens.hash_token, the same helper already used for
  refresh/verification/reset tokens elsewhere in this codebase) — the raw
  codes are shown to the user exactly once, at confirm time, and are never
  recoverable afterward, matching how every other secret in this app is
  handled.
"""
from __future__ import annotations

import base64
import io
import secrets

import pyotp
import qrcode

_ISSUER = "Survival School"
BACKUP_CODE_COUNT = 8


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=_ISSUER)


def qr_code_data_uri(otpauth_url: str) -> str:
    img = qrcode.make(otpauth_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def verify_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    # valid_window=1 tolerates the code from one 30s step before/after now,
    # the standard allowance for clock drift between the server and the
    # user's phone — without it, a phone even a few seconds out of sync
    # produces constant false rejections.
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def generate_backup_codes() -> list[str]:
    """Human-typeable backup codes: 8 codes x 16 hex chars = 64 bits each.
    Online guessing is already effectively impossible regardless of length
    (POST /auth/2fa/verify-login rate-limits to 10 attempts/5min per IP AND
    per user — see app/api/v1/auth.py) — the length here specifically
    matters for the "database leaked" threat model instead: these are
    hashed with the same unsalted SHA-256 used for refresh/verification
    tokens elsewhere (security.tokens.hash_token), so an attacker with a DB
    dump can brute-force the hashes offline at billions/sec on a GPU with
    no rate limit at all. 32 bits (the previous length) falls in under an
    hour that way; 64 bits does not fall to brute force at any practical
    scale."""
    return [secrets.token_hex(8).upper() for _ in range(BACKUP_CODE_COUNT)]
