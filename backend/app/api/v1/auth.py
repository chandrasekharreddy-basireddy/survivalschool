from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_client_ip, get_current_user
from app.models.user import EmailVerification, PasswordReset, RefreshToken, Role, User
from app.models.user import Session as SessionModel
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)
from app.security.passwords import hash_password, verify_password, verify_password_dummy
from app.security.tokens import (
    create_access_token,
    hash_token,
    new_email_verification_token,
    new_password_reset_token,
    new_refresh_token_pair,
)
from app.services.analytics_service import track_event
from app.services.audit_service import record_audit_event
from app.services.email_service import send_email
from app.services.n8n_service import emit_event
from app.services.notification_service import notify_security_event
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


async def _load_user_with_roles(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


async def _issue_tokens(db: AsyncSession, user: User, request: Request, device_label: str | None) -> TokenResponse:
    session_row = SessionModel(
        user_id=user.id,
        device_label=device_label,
        user_agent=request.headers.get("user-agent"),
        ip_address=get_client_ip(request),
    )
    db.add(session_row)
    await db.flush()

    access_token = create_access_token(user.id, [r.name for r in user.roles], session_row.id)
    raw_refresh, refresh_hash, refresh_expires = new_refresh_token_pair()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            session_id=session_row.id,
            expires_at=refresh_expires,
        )
    )
    await db.flush()
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
    )


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"register:{get_client_ip(request)}", limit=settings.RATE_LIMIT_REGISTER_PER_HOUR, window_seconds=3600)

    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none() is not None:
        # Same response either way would leak less, but registration UX needs a clear
        # "already exists" — we accept that tradeoff here (unlike login, which stays generic).
        raise ConflictError("An account with this email already exists.")

    student_role = (await db.execute(select(Role).where(Role.name == "STUDENT"))).scalar_one_or_none()
    if student_role is None:
        raise ValidationAppError("STUDENT role is not seeded. Run database seed script.")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_email_verified=False,
    )
    user.roles.append(student_role)
    db.add(user)
    await db.flush()

    raw_token, token_hash, expires_at = new_email_verification_token()
    db.add(EmailVerification(user_id=user.id, token_hash=token_hash, expires_at=expires_at))

    await record_audit_event(
        db, actor_id=user.id, action="user.register", resource_type="user", resource_id=str(user.id),
        ip_address=get_client_ip(request),
    )
    await track_event(db, event_type="registration", user_id=user.id, source="web")
    await db.commit()

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
    await send_email(
        user.email, f"Verify your {settings.APP_NAME} account", "verify_email",
        full_name=user.full_name, verify_url=verify_url, ttl_hours=settings.EMAIL_VERIFICATION_TTL_HOURS,
    )
    await emit_event("student.registered", {"email": user.email, "full_name": user.full_name})

    return UserOut(id=user.id, email=user.email, full_name=user.full_name,
                    is_email_verified=user.is_email_verified, roles=["STUDENT"])


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(payload.token)
    result = await db.execute(select(EmailVerification).where(EmailVerification.token_hash == token_hash))
    record = result.scalar_one_or_none()

    if record is None:
        raise NotFoundError("Verification token is invalid.", code="invalid_token")
    if record.used_at is not None:
        return MessageResponse(message="Email already verified.")
    if record.expires_at < datetime.now(timezone.utc):
        raise ValidationAppError("Verification token has expired. Request a new one.", code="token_expired")

    user = await db.get(User, record.user_id)
    if user is None:
        raise NotFoundError("Account not found.")

    user.is_email_verified = True
    record.used_at = datetime.now(timezone.utc)
    await record_audit_event(db, actor_id=user.id, action="user.verify_email", resource_type="user", resource_id=str(user.id))
    await db.commit()

    await send_email(
        user.email, f"Welcome to {settings.APP_NAME}", "welcome",
        full_name=user.full_name, dashboard_url=f"{settings.FRONTEND_URL}/dashboard",
    )
    return MessageResponse(message="Email verified successfully.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(payload: ResendVerificationRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"resend-verify:{payload.email.lower()}", limit=settings.RATE_LIMIT_RESEND_VERIFY_PER_HOUR, window_seconds=3600)

    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    # Always return the same generic message — never reveal whether the account exists.
    generic = MessageResponse(message="If that account exists and is unverified, a new verification email has been sent.")
    if user is None or user.is_email_verified:
        return generic

    raw_token, token_hash, expires_at = new_email_verification_token()
    db.add(EmailVerification(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
    await send_email(
        user.email, f"Verify your {settings.APP_NAME} account", "verify_email",
        full_name=user.full_name, verify_url=verify_url, ttl_hours=settings.EMAIL_VERIFICATION_TTL_HOURS,
    )
    return generic


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"login:{get_client_ip(request)}", limit=settings.RATE_LIMIT_LOGIN_PER_5MIN, window_seconds=300)
    await enforce_rate_limit(f"login-email:{payload.email.lower()}", limit=settings.RATE_LIMIT_LOGIN_PER_5MIN, window_seconds=300)

    result = await db.execute(
        select(User).where(User.email == payload.email.lower())
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()

    generic_error = AuthenticationError("Invalid email or password.", code="invalid_credentials")

    if user is None:
        # Burn the same Argon2id verify cost the "user exists, wrong password"
        # branch below pays, so response latency can't be used to enumerate
        # which emails have accounts even though the error message is identical.
        verify_password_dummy()
        raise generic_error

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise AuthenticationError(
            "Account is temporarily locked due to repeated failed sign-in attempts.",
            code="account_locked",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            from datetime import timedelta
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCOUNT_LOCK_MINUTES)
            await record_audit_event(db, actor_id=user.id, action="user.account_locked", resource_type="user",
                                      resource_id=str(user.id), result="failure", ip_address=get_client_ip(request))
        await db.commit()
        raise generic_error

    if not user.is_active or user.deleted_at is not None:
        raise AuthenticationError("Account is disabled.", code="account_disabled")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)

    tokens = await _issue_tokens(db, user, request, payload.device_label)
    await record_audit_event(db, actor_id=user.id, action="user.login", resource_type="user",
                              resource_id=str(user.id), ip_address=get_client_ip(request))
    await track_event(db, event_type="login", user_id=user.id, source="web")
    await db.commit()

    await notify_security_event(
        db, user, "login_alert", "New sign-in to your account",
        device_label=payload.device_label, ip_address=get_client_ip(request),
    )
    await db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    record = result.scalar_one_or_none()

    if record is None:
        raise AuthenticationError("Invalid refresh token.")
    if record.revoked_at is not None:
        # Reuse of a revoked/rotated refresh token is a strong signal of token theft:
        # revoke the entire session defensively.
        session_row = await db.get(SessionModel, record.session_id)
        if session_row:
            session_row.revoked_at = datetime.now(timezone.utc)
        await record_audit_event(db, actor_id=record.user_id, action="auth.refresh_reuse_detected",
                                  resource_type="session", resource_id=str(record.session_id), result="failure")
        await db.commit()
        raise AuthenticationError("Refresh token has been revoked. Please log in again.", code="token_reuse_detected")
    if record.expires_at < datetime.now(timezone.utc):
        raise AuthenticationError("Refresh token expired. Please log in again.")

    user = await _load_user_with_roles(db, record.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is not active.")

    # Rotate: revoke old, issue new (prevents replay).
    record.revoked_at = datetime.now(timezone.utc)
    access_token = create_access_token(user.id, [r.name for r in user.roles], record.session_id)
    raw_refresh, new_hash, new_expires = new_refresh_token_pair()
    new_record = RefreshToken(user_id=user.id, token_hash=new_hash, session_id=record.session_id, expires_at=new_expires)
    db.add(new_record)
    await db.flush()
    record.replaced_by_id = new_record.id

    session_row = await db.get(SessionModel, record.session_id)
    if session_row:
        session_row.last_seen_at = datetime.now(timezone.utc)

    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh, expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60)


@router.post("/logout", response_model=MessageResponse)
async def logout(payload: RefreshRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.user_id == user.id))
    record = result.scalar_one_or_none()
    if record:
        record.revoked_at = datetime.now(timezone.utc)
        session_row = await db.get(SessionModel, record.session_id)
        if session_row:
            session_row.revoked_at = datetime.now(timezone.utc)
    await record_audit_event(db, actor_id=user.id, action="user.logout", resource_type="user", resource_id=str(user.id))
    await db.commit()
    return MessageResponse(message="Logged out.")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    sessions = (await db.execute(select(SessionModel).where(SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None)))).scalars().all()
    for s in sessions:
        s.revoked_at = now
    tokens = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)))).scalars().all()
    for t in tokens:
        t.revoked_at = now
    await record_audit_event(db, actor_id=user.id, action="user.logout_all_sessions", resource_type="user", resource_id=str(user.id))
    await db.commit()
    return MessageResponse(message=f"Signed out of {len(sessions)} session(s).")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"forgot-pw:{payload.email.lower()}", limit=settings.RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR, window_seconds=3600)
    generic = MessageResponse(message="If that account exists, a password reset email has been sent.")

    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None:
        return generic

    raw_token, token_hash, expires_at = new_password_reset_token()
    db.add(PasswordReset(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await record_audit_event(db, actor_id=user.id, action="user.password_reset_requested", resource_type="user", resource_id=str(user.id))
    await db.commit()

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
    await send_email(
        user.email, "Reset your password", "password_reset",
        full_name=user.full_name, reset_url=reset_url, ttl_minutes=settings.PASSWORD_RESET_TTL_MINUTES,
    )
    return generic


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(payload.token)
    result = await db.execute(select(PasswordReset).where(PasswordReset.token_hash == token_hash))
    record = result.scalar_one_or_none()

    if record is None:
        raise NotFoundError("Reset token is invalid.", code="invalid_token")
    if record.used_at is not None:
        raise ValidationAppError("This reset link has already been used.", code="token_used")
    if record.expires_at < datetime.now(timezone.utc):
        raise ValidationAppError("Reset token has expired. Request a new one.", code="token_expired")

    user = await db.get(User, record.user_id)
    if user is None:
        raise NotFoundError("Account not found.")

    user.password_hash = hash_password(payload.new_password)
    record.used_at = datetime.now(timezone.utc)

    # Defense in depth: a password reset revokes every existing session/refresh token.
    now = datetime.now(timezone.utc)
    for s in (await db.execute(select(SessionModel).where(SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None)))).scalars().all():
        s.revoked_at = now
    for t in (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)))).scalars().all():
        t.revoked_at = now

    await record_audit_event(db, actor_id=user.id, action="user.password_reset_completed", resource_type="user", resource_id=str(user.id))
    await db.commit()
    return MessageResponse(message="Password has been reset. Please log in again.")


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email, full_name=user.full_name,
                    is_email_verified=user.is_email_verified, roles=[r.name for r in user.roles])
