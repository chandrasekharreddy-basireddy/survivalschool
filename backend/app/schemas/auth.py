from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.security.passwords import PASSWORD_POLICY_MESSAGE, validate_password_policy


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)

    @field_validator("password")
    @classmethod
    def _password_policy(cls, v: str) -> str:
        if not validate_password_policy(v):
            raise ValueError(PASSWORD_POLICY_MESSAGE)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_label: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MFAChallengeOut(BaseModel):
    """Returned by POST /auth/login instead of TokenResponse when the
    account has TOTP enabled — password was correct, but real tokens are
    withheld until POST /auth/2fa/verify-login also confirms the code."""
    mfa_required: bool = True
    mfa_token: str


class TwoFactorSetupOut(BaseModel):
    secret: str
    otpauth_url: str
    qr_code_data_uri: str


class TwoFactorConfirmIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TwoFactorConfirmOut(BaseModel):
    backup_codes: list[str]


class TwoFactorDisableIn(BaseModel):
    password: str


class TwoFactorLoginVerify(BaseModel):
    mfa_token: str
    # Accepts either a 6-digit TOTP code or a 16-char backup code (see
    # totp_service.generate_backup_codes) — max_length gives a little slack
    # above 16 for incidental whitespace a user might paste in, which gets
    # stripped before comparison in the /2fa/verify-login handler.
    code: str = Field(min_length=6, max_length=24)


class RefreshRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password_policy(cls, v: str) -> str:
        if not validate_password_policy(v):
            raise ValueError(PASSWORD_POLICY_MESSAGE)
        return v


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_email_verified: bool
    is_active: bool = True
    totp_enabled: bool = False
    roles: list[str]

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
