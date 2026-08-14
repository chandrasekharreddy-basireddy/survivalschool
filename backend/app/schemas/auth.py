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
    roles: list[str]

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
