from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt as pyjwt
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationAppError,
)
from app.database import get_db
from app.dependencies import (
    get_client_ip,
    get_current_session_id,
    get_current_user,
    get_current_user_optional,
    get_current_verified_user,
)
from app.models.user import (
    EmailVerification,
    InstructorApplication,
    PasswordReset,
    RefreshToken,
    Role,
    User,
    WebAuthnCredential,
)
from app.models.user import Session as SessionModel
from app.redis_client import get_redis
from app.schemas.auth import (
    ForgotPasswordRequest,
    InstructorApplicationCreate,
    InstructorApplicationOut,
    LoginRequest,
    MessageResponse,
    MFAChallengeOut,
    PasskeyLoginOptionsIn,
    PasskeyLoginVerifyIn,
    PasskeyOut,
    PasskeyRegisterVerifyIn,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionOut,
    TokenResponse,
    TwoFactorConfirmIn,
    TwoFactorConfirmOut,
    TwoFactorDisableIn,
    TwoFactorLoginVerify,
    TwoFactorSetupOut,
    UserOut,
    VerifyEmailRequest,
)
from app.security.passwords import hash_password, verify_password, verify_password_dummy
from app.security.tokens import (
    create_access_token,
    create_mfa_pending_token,
    decode_mfa_pending_token,
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
from app.services.profile_service import create_profile_with_handle
from app.services.rate_limit_service import enforce_rate_limit
from app.services.totp_service import (
    generate_backup_codes,
    generate_secret,
    provisioning_uri,
    qr_code_data_uri,
    verify_code,
)

# Redis TTL for a stashed WebAuthn challenge -- long enough for a user to
# pick an authenticator and complete a biometric/PIN prompt, short enough
# that a stale challenge can't be replayed much later.
_WEBAUTHN_CHALLENGE_TTL_SECONDS = 300

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = structlog.get_logger("survivalschool.auth")


async def _load_user_with_roles(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


async def _is_known_device(db: AsyncSession, user_id: uuid.UUID, request: Request) -> bool:
    """Has this user ever signed in with this exact User-Agent before? Used
    to gate the login-alert email to genuinely NEW devices instead of firing
    on every single login -- must be called before _issue_tokens() creates
    this login's own session row, or it would always match itself."""
    user_agent = request.headers.get("user-agent")
    if not user_agent:
        return False
    existing = (await db.execute(
        select(SessionModel.id).where(SessionModel.user_id == user_id, SessionModel.user_agent == user_agent).limit(1)
    )).scalar_one_or_none()
    return existing is not None


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
    try:
        await db.flush()
    except IntegrityError as exc:
        # The pre-check above is a plain read-then-insert, not a lock — two
        # near-simultaneous registrations for the same email (a double-
        # clicked submit, a client retry) can both pass it before either
        # commits. Without this, the second request's flush hit the DB's
        # unique constraint on users.email as a raw, unhandled
        # IntegrityError, surfacing to the user as a generic 500 instead of
        # the same clean "already exists" response the common case gets.
        await db.rollback()
        raise ConflictError("An account with this email already exists.") from exc

    # Every account gets its unique @handle up front — it's how people find
    # each other for connections, elimination-battle invites/lobbies, etc.
    # throughout the app, so there's no "unnamed user" state to fall back
    # to later. A claim collision here rolls back the whole registration
    # (nothing has been committed yet) and surfaces as a clean 409.
    await create_profile_with_handle(db, user.id, payload.username)

    raw_token, token_hash, expires_at = new_email_verification_token()
    db.add(EmailVerification(user_id=user.id, token_hash=token_hash, expires_at=expires_at))

    await record_audit_event(
        db, actor_id=user.id, action="user.register", resource_type="user", resource_id=str(user.id),
        ip_address=get_client_ip(request),
    )
    await track_event(db, event_type="registration", user_id=user.id, source="web")
    await db.commit()

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
    # The account is already committed at this point -- a real email delivery
    # failure (bad SMTP creds, provider outage, unverified sender domain,
    # etc.) must not roll back a successful registration. But send_email()
    # returning False is a real signal the caller shouldn't just discard: the
    # user has no other way to learn their verification link never arrived.
    email_delivery_ok = await send_email(
        user.email, f"Verify your {settings.APP_NAME} account", "verify_email",
        full_name=user.full_name, verify_url=verify_url, ttl_hours=settings.EMAIL_VERIFICATION_TTL_HOURS,
    )
    await emit_event("student.registered", {"email": user.email, "full_name": user.full_name})

    return UserOut(id=user.id, email=user.email, full_name=user.full_name,
                    is_email_verified=user.is_email_verified, roles=["STUDENT"],
                    email_delivery_ok=email_delivery_ok)


@router.post("/instructor-applications", response_model=InstructorApplicationOut, status_code=201)
async def apply_as_instructor(
    payload: InstructorApplicationCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Apply to teach on the platform. Deliberately NOT gated by the Thursday
    student registration window — that window controls admission to the
    weekly exam cohort, which instructors aren't part of — and deliberately
    does NOT grant the INSTRUCTOR role directly. It only records a pending
    application; an admin reviews it via the admin endpoints below and, on
    approval, grants the role through the existing audited role-assignment
    path. Works two ways: an already-signed-in user applies with just a
    reason, or a brand-new applicant supplies email/password/full_name and an
    account is created for them (unverified, same as normal registration)."""
    await enforce_rate_limit(
        f"instructor-apply:{get_client_ip(request)}", limit=settings.RATE_LIMIT_REGISTER_PER_HOUR, window_seconds=3600
    )

    email_delivery_ok = True
    if user is None:
        if not payload.email or not payload.password or not payload.full_name or not payload.username:
            raise ValidationAppError(
                "email, password, full_name, and username are required when applying without an existing account."
            )
        existing = await db.execute(select(User).where(User.email == payload.email.lower()))
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(
                "An account with this email already exists. Sign in, then apply from your account."
            )
        student_role = (await db.execute(select(Role).where(Role.name == "STUDENT"))).scalar_one_or_none()
        if student_role is None:
            raise ValidationAppError("STUDENT role is not seeded. Run database seed script.")

        user = User(
            email=payload.email.lower(), password_hash=hash_password(payload.password),
            full_name=payload.full_name, is_email_verified=False,
        )
        user.roles.append(student_role)
        db.add(user)
        try:
            await db.flush()
        except IntegrityError as exc:
            # Same race as register() above — the pre-check isn't a lock.
            await db.rollback()
            raise ConflictError(
                "An account with this email already exists. Sign in, then apply from your account."
            ) from exc
        await create_profile_with_handle(db, user.id, payload.username)

        raw_token, token_hash, expires_at = new_email_verification_token()
        db.add(EmailVerification(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        verify_url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
        email_delivery_ok = await send_email(
            user.email, f"Verify your {settings.APP_NAME} account", "verify_email",
            full_name=user.full_name, verify_url=verify_url, ttl_hours=settings.EMAIL_VERIFICATION_TTL_HOURS,
        )

    existing_application = (await db.execute(
        select(InstructorApplication).where(
            InstructorApplication.user_id == user.id, InstructorApplication.status == "pending"
        )
    )).scalar_one_or_none()
    if existing_application is not None:
        raise ConflictError("You already have a pending instructor application.")

    application = InstructorApplication(
        user_id=user.id, institution=payload.institution, reason=payload.reason,
    )
    db.add(application)
    await record_audit_event(
        db, actor_id=user.id, action="instructor_application.submitted",
        resource_type="instructor_application", ip_address=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(application)

    background_tasks.add_task(emit_event, "instructor.application_submitted", {
        "email": user.email, "full_name": user.full_name, "institution": payload.institution,
    })

    return InstructorApplicationOut(
        id=application.id, user_id=user.id, applicant_email=user.email, applicant_name=user.full_name,
        institution=application.institution, reason=application.reason, status=application.status,
        created_at=application.created_at, reviewed_at=application.reviewed_at,
        review_note=application.review_note, email_delivery_ok=email_delivery_ok,
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: VerifyEmailRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"verify-email-ip:{get_client_ip(request)}", limit=settings.RATE_LIMIT_TOKEN_ENDPOINT_PER_HOUR_PER_IP, window_seconds=3600)
    token_hash = hash_token(payload.token)
    result = await db.execute(select(EmailVerification).where(EmailVerification.token_hash == token_hash))
    record = result.scalar_one_or_none()

    if record is None:
        raise NotFoundError("Verification token is invalid.", code="invalid_token")
    if record.used_at is not None:
        return MessageResponse(message="Email already verified.")
    if record.expires_at < datetime.now(UTC):
        raise ValidationAppError("Verification token has expired. Request a new one.", code="token_expired")

    user = await db.get(User, record.user_id)
    if user is None:
        raise NotFoundError("Account not found.")

    user.is_email_verified = True
    record.used_at = datetime.now(UTC)
    await record_audit_event(db, actor_id=user.id, action="user.verify_email", resource_type="user", resource_id=str(user.id))
    await db.commit()

    await send_email(
        user.email, f"Welcome to {settings.APP_NAME}", "welcome",
        full_name=user.full_name, dashboard_url=f"{settings.FRONTEND_URL}/dashboard",
    )
    return MessageResponse(message="Email verified successfully.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(payload: ResendVerificationRequest, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"resend-verify:{payload.email.lower()}", limit=settings.RATE_LIMIT_RESEND_VERIFY_PER_HOUR, window_seconds=3600)
    await enforce_rate_limit(f"resend-verify-ip:{get_client_ip(request)}", limit=settings.RATE_LIMIT_RESEND_VERIFY_PER_HOUR_PER_IP, window_seconds=3600)

    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    # Always return the same generic message — never reveal whether the account exists.
    generic = MessageResponse(message="If that account exists and is unverified, a new verification email has been sent.")
    if user is None or user.is_email_verified:
        return generic

    raw_token, token_hash, expires_at = new_email_verification_token()
    db.add(EmailVerification(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()

    # Sending is deferred to a background task, after the response is on the
    # wire: login already had a timing defense (verify_password_dummy) against
    # an attacker inferring account existence from response latency, but this
    # endpoint had none — it awaited a real HTTPS call to the email provider
    # (tens-hundreds of ms) only on the "account exists" path, while the
    # "doesn't exist" path returned almost instantly. Deferring the send makes
    # both paths return in comparable time regardless of the account's
    # existence.
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
    background_tasks.add_task(
        send_email,
        user.email, f"Verify your {settings.APP_NAME} account", "verify_email",
        full_name=user.full_name, verify_url=verify_url, ttl_hours=settings.EMAIL_VERIFICATION_TTL_HOURS,
    )
    return generic


@router.post("/login", response_model=TokenResponse | MFAChallengeOut)
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

    if user.locked_until and user.locked_until > datetime.now(UTC):
        raise AuthenticationError(
            "Account is temporarily locked due to repeated failed sign-in attempts.",
            code="account_locked",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            from datetime import timedelta
            user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.ACCOUNT_LOCK_MINUTES)
            await record_audit_event(db, actor_id=user.id, action="user.account_locked", resource_type="user",
                                      resource_id=str(user.id), result="failure", ip_address=get_client_ip(request))
        await db.commit()
        raise generic_error

    if not user.is_active or user.deleted_at is not None:
        # Deliberately the SAME generic error as a wrong password, not a
        # distinct "Account is disabled." — that would hand an attacker a
        # password-correctness oracle for accounts that can't even log in
        # (confirm a breached/guessed credential is right without ever
        # needing it to work). A legitimately disabled user not getting an
        # explanatory error here is the accepted tradeoff; they're expected
        # to be told out-of-band (support, the admin who disabled them) —
        # same reasoning login already applies to account-existence via
        # the identical wrong-password/no-such-user error above.
        await record_audit_event(db, actor_id=user.id, action="user.login_blocked_disabled", resource_type="user",
                                  resource_id=str(user.id), result="failure", ip_address=get_client_ip(request))
        await db.commit()
        raise generic_error

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(UTC)

    if user.totp_enabled:
        # Password was correct, but real tokens are withheld until the
        # matching TOTP/backup code is also verified — see
        # POST /auth/2fa/verify-login and create_mfa_pending_token's
        # docstring for why this can't be used as a bearer token anywhere.
        mfa_token = create_mfa_pending_token(user.id)
        await record_audit_event(db, actor_id=user.id, action="user.login_mfa_challenge", resource_type="user",
                                  resource_id=str(user.id), ip_address=get_client_ip(request))
        await db.commit()
        return MFAChallengeOut(mfa_token=mfa_token)

    is_new_device = not await _is_known_device(db, user.id, request)
    tokens = await _issue_tokens(db, user, request, payload.device_label)
    await record_audit_event(db, actor_id=user.id, action="user.login", resource_type="user",
                              resource_id=str(user.id), ip_address=get_client_ip(request))
    await track_event(db, event_type="login", user_id=user.id, source="web")
    await db.commit()

    # The login already succeeded and committed above. The security-alert
    # notification is a best-effort side effect: if it (or its own commit)
    # fails, log it and still return valid tokens rather than turning a
    # successful sign-in into a 500 the user can do nothing about. Only sent
    # for a device (User-Agent) this account hasn't signed in from before --
    # otherwise every routine login would trigger it.
    if is_new_device:
        try:
            await notify_security_event(
                db, user, "login_alert", "New sign-in to your account",
                device_label=payload.device_label, ip_address=get_client_ip(request),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("login_alert_notify_failed", user_id=str(user.id))
    return tokens


@router.post("/2fa/verify-login", response_model=TokenResponse)
async def verify_2fa_login(payload: TwoFactorLoginVerify, request: Request, db: AsyncSession = Depends(get_db)):
    """Second step of login for accounts with TOTP enabled. Takes the
    mfa_token from the MFAChallengeOut response plus a 6-digit TOTP code
    (or an 8-character backup code) and, if valid, issues real tokens via
    the exact same _issue_tokens/audit/notify path a normal password-only
    login uses."""
    await enforce_rate_limit(f"2fa-verify:{get_client_ip(request)}", limit=10, window_seconds=300)

    try:
        mfa_payload = decode_mfa_pending_token(payload.mfa_token)
    except pyjwt.PyJWTError as exc:
        raise AuthenticationError("Your sign-in session expired — please log in again.", code="mfa_session_expired") from exc

    user = await _load_user_with_roles(db, uuid.UUID(mfa_payload["sub"]))
    if user is None or not user.totp_enabled or not user.is_active or user.deleted_at is not None:
        raise AuthenticationError("Your sign-in session expired — please log in again.", code="mfa_session_expired")

    await enforce_rate_limit(f"2fa-verify-user:{user.id}", limit=10, window_seconds=300)

    verified = verify_code(user.totp_secret, payload.code)
    if not verified:
        # Fall back to a one-time backup code — normalize the same way
        # they were generated (upper-case hex, see totp_service.generate_
        # backup_codes) before hashing and comparing.
        #
        # Re-read the user row under a lock before checking/consuming the
        # code: without it, two concurrent requests presenting the SAME
        # backup code can both see it in the list before either commits its
        # removal, and both get a valid session from a single-use code.
        # with_for_update makes the second request wait for the first to
        # commit, at which point the code is already gone from the list.
        normalized = payload.code.strip().upper().replace(" ", "")
        code_hash = hash_token(normalized)
        locked_user = await db.get(User, user.id, with_for_update=True)
        if locked_user is not None and code_hash in (locked_user.totp_backup_codes or []):
            verified = True
            locked_user.totp_backup_codes = [c for c in locked_user.totp_backup_codes if c != code_hash]

    if not verified:
        await record_audit_event(db, actor_id=user.id, action="user.login_mfa_failed", resource_type="user",
                                  resource_id=str(user.id), result="failure", ip_address=get_client_ip(request))
        await db.commit()
        raise AuthenticationError("Invalid authentication code.", code="invalid_2fa_code")

    is_new_device = not await _is_known_device(db, user.id, request)
    tokens = await _issue_tokens(db, user, request, None)
    await record_audit_event(db, actor_id=user.id, action="user.login", resource_type="user",
                              resource_id=str(user.id), ip_address=get_client_ip(request))
    await track_event(db, event_type="login", user_id=user.id, source="web")
    await db.commit()

    # Best-effort post-login alert, new devices only — see the note on the password login path.
    if is_new_device:
        try:
            await notify_security_event(
                db, user, "login_alert", "New sign-in to your account",
                device_label=None, ip_address=get_client_ip(request),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("login_alert_notify_failed", user_id=str(user.id))
    return tokens


@router.post("/2fa/setup", response_model=TwoFactorSetupOut)
async def setup_2fa(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Step 1: generate a new secret and return a QR code to scan into an
    authenticator app. This does NOT enable 2FA yet — the secret is
    "pending" until POST /auth/2fa/confirm proves the app actually has it,
    so a user can't get locked out by a secret their app never saved."""
    if user.totp_enabled:
        raise ConflictError("Two-factor authentication is already enabled. Disable it first to re-set-up.")
    secret = generate_secret()
    user.totp_secret = secret
    await db.commit()
    otpauth_url = provisioning_uri(secret, user.email)
    return TwoFactorSetupOut(secret=secret, otpauth_url=otpauth_url, qr_code_data_uri=qr_code_data_uri(otpauth_url))


@router.post("/2fa/confirm", response_model=TwoFactorConfirmOut)
async def confirm_2fa(payload: TwoFactorConfirmIn, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Step 2: prove the authenticator app in step 1 actually works, then
    flip totp_enabled on and hand back one-time backup codes — shown to the
    user exactly once here, never recoverable afterward (only their SHA-256
    hashes are stored)."""
    await enforce_rate_limit(f"2fa-verify:{user.id}", limit=settings.RATE_LIMIT_2FA_VERIFY_PER_5MIN, window_seconds=300)
    if not user.totp_secret:
        raise ValidationAppError("Start setup first via POST /auth/2fa/setup.")
    if user.totp_enabled:
        raise ConflictError("Two-factor authentication is already enabled.")
    if not verify_code(user.totp_secret, payload.code):
        raise ValidationAppError("Incorrect code — check your authenticator app and try again.")

    backup_codes = generate_backup_codes()
    user.totp_backup_codes = [hash_token(c) for c in backup_codes]
    user.totp_enabled = True
    await record_audit_event(db, actor_id=user.id, action="user.2fa_enabled", resource_type="user", resource_id=str(user.id))
    await db.commit()
    return TwoFactorConfirmOut(backup_codes=backup_codes)


@router.post("/2fa/disable", response_model=MessageResponse)
async def disable_2fa(payload: TwoFactorDisableIn, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Requires re-entering the account password (not just an active
    session) — disabling 2FA is a security-downgrading action, same bar as
    changing a password elsewhere in this app."""
    await enforce_rate_limit(f"2fa-verify:{user.id}", limit=settings.RATE_LIMIT_2FA_VERIFY_PER_5MIN, window_seconds=300)
    if not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Incorrect password.")
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_backup_codes = []
    await record_audit_event(db, actor_id=user.id, action="user.2fa_disabled", resource_type="user", resource_id=str(user.id))
    await db.commit()
    return MessageResponse(message="Two-factor authentication has been disabled.")


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
            session_row.revoked_at = datetime.now(UTC)
        await record_audit_event(db, actor_id=record.user_id, action="auth.refresh_reuse_detected",
                                  resource_type="session", resource_id=str(record.session_id), result="failure")
        await db.commit()
        raise AuthenticationError("Refresh token has been revoked. Please log in again.", code="token_reuse_detected")
    if record.expires_at < datetime.now(UTC):
        raise AuthenticationError("Refresh token expired. Please log in again.")

    user = await _load_user_with_roles(db, record.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is not active.")

    # Rotate: revoke old, issue new (prevents replay).
    record.revoked_at = datetime.now(UTC)
    access_token = create_access_token(user.id, [r.name for r in user.roles], record.session_id)
    raw_refresh, new_hash, new_expires = new_refresh_token_pair()
    new_record = RefreshToken(user_id=user.id, token_hash=new_hash, session_id=record.session_id, expires_at=new_expires)
    db.add(new_record)
    await db.flush()
    record.replaced_by_id = new_record.id

    session_row = await db.get(SessionModel, record.session_id)
    if session_row:
        session_row.last_seen_at = datetime.now(UTC)

    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh, expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60)


@router.post("/logout", response_model=MessageResponse)
async def logout(payload: RefreshRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.user_id == user.id))
    record = result.scalar_one_or_none()
    if record:
        record.revoked_at = datetime.now(UTC)
        session_row = await db.get(SessionModel, record.session_id)
        if session_row:
            session_row.revoked_at = datetime.now(UTC)
    await record_audit_event(db, actor_id=user.id, action="user.logout", resource_type="user", resource_id=str(user.id))
    await db.commit()
    return MessageResponse(message="Logged out.")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(UTC)
    sessions = (await db.execute(select(SessionModel).where(SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None)))).scalars().all()
    for s in sessions:
        s.revoked_at = now
    tokens = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)))).scalars().all()
    for t in tokens:
        t.revoked_at = now
    await record_audit_event(db, actor_id=user.id, action="user.logout_all_sessions", resource_type="user", resource_id=str(user.id))
    await db.commit()
    return MessageResponse(message=f"Signed out of {len(sessions)} session(s).")


def _friendly_device_label(user_agent: str | None) -> str | None:
    """A short, human-readable "Browser on OS" label from a raw User-Agent
    string, without pulling in a full UA-parsing dependency for what's
    ultimately just a display hint — never used for any security decision."""
    if not user_agent:
        return None
    ua = user_agent
    if "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "Mac OS X" in ua:
        os_name = "macOS"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = None

    if "Edg/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "CriOS" in ua or "Chrome/" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = None

    if browser and os_name:
        return f"{browser} on {os_name}"
    return browser or os_name


@router.get("/sessions", response_model=list[SessionOut])
async def list_my_sessions(
    user: User = Depends(get_current_user),
    current_session_id: uuid.UUID = Depends(get_current_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Every device/browser currently signed in to this account — the
    self-service view of what /auth/logout-all nukes indiscriminately, so a
    user can spot and revoke just the one they don't recognize."""
    sessions = (await db.execute(
        select(SessionModel)
        .where(SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None))
        .order_by(SessionModel.last_seen_at.desc())
    )).scalars().all()
    return [
        SessionOut(
            id=s.id,
            device_label=s.device_label or _friendly_device_label(s.user_agent),
            ip_address=s.ip_address,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            is_current=s.id == current_session_id,
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_my_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sign out one specific device — the targeted counterpart to
    /auth/logout-all. Scoped to the caller's own sessions only: the path
    parameter is a bare id with no ownership check built in by FastAPI, so
    the WHERE clause below is what actually stops one user from revoking
    another's session by guessing/enumerating ids."""
    session_row = (await db.execute(
        select(SessionModel).where(SessionModel.id == session_id, SessionModel.user_id == user.id)
    )).scalar_one_or_none()
    if session_row is None:
        raise NotFoundError("Session not found.")
    if session_row.revoked_at is None:
        now = datetime.now(UTC)
        session_row.revoked_at = now
        for t in (await db.execute(
            select(RefreshToken).where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
        )).scalars().all():
            t.revoked_at = now
        await record_audit_event(
            db, actor_id=user.id, action="user.session_revoked", resource_type="session",
            resource_id=str(session_id),
        )
        await db.commit()
    return MessageResponse(message="Session signed out.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"forgot-pw:{payload.email.lower()}", limit=settings.RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR, window_seconds=3600)
    await enforce_rate_limit(f"forgot-pw-ip:{get_client_ip(request)}", limit=settings.RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR_PER_IP, window_seconds=3600)
    generic = MessageResponse(message="If that account exists, a password reset email has been sent.")

    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None:
        return generic

    raw_token, token_hash, expires_at = new_password_reset_token()
    db.add(PasswordReset(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await record_audit_event(db, actor_id=user.id, action="user.password_reset_requested", resource_type="user", resource_id=str(user.id))
    await db.commit()

    # See the matching comment on resend_verification: deferring the send to
    # a background task closes the timing side-channel between "account
    # exists" (used to await a real email-provider HTTPS call here) and
    # "doesn't exist" (returned immediately).
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
    background_tasks.add_task(
        send_email,
        user.email, "Reset your password", "password_reset",
        full_name=user.full_name, reset_url=reset_url, ttl_minutes=settings.PASSWORD_RESET_TTL_MINUTES,
    )
    return generic


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"reset-pw-ip:{get_client_ip(request)}", limit=settings.RATE_LIMIT_TOKEN_ENDPOINT_PER_HOUR_PER_IP, window_seconds=3600)
    token_hash = hash_token(payload.token)
    result = await db.execute(select(PasswordReset).where(PasswordReset.token_hash == token_hash))
    record = result.scalar_one_or_none()

    if record is None:
        raise NotFoundError("Reset token is invalid.", code="invalid_token")
    if record.used_at is not None:
        raise ValidationAppError("This reset link has already been used.", code="token_used")
    if record.expires_at < datetime.now(UTC):
        raise ValidationAppError("Reset token has expired. Request a new one.", code="token_expired")

    user = await db.get(User, record.user_id)
    if user is None:
        raise NotFoundError("Account not found.")

    user.password_hash = hash_password(payload.new_password)
    now = datetime.now(UTC)
    record.used_at = now

    # Invalidate every OTHER outstanding, unused reset token for this account
    # too — not just the one just redeemed. Without this, an older reset
    # email (forwarded, intercepted, or just requested twice) stays valid
    # after the account owner already changed their password, letting
    # whoever holds that link reset it again later with no warning to the
    # real owner.
    for other in (await db.execute(
        select(PasswordReset).where(
            PasswordReset.user_id == user.id,
            PasswordReset.id != record.id,
            PasswordReset.used_at.is_(None),
        )
    )).scalars().all():
        other.used_at = now

    # Defense in depth: a password reset revokes every existing session/refresh token.
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
                    is_email_verified=user.is_email_verified, totp_enabled=user.totp_enabled,
                    roles=[r.name for r in user.roles])


@router.post("/passkeys/register/options")
async def passkey_register_options(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Step 1 of adding a passkey to an already-logged-in account (Settings
    -> Add a passkey). Not a signup flow -- passkeys are an additional
    factor an existing account opts into, same relationship 2FA has to the
    password login above."""
    await enforce_rate_limit(f"passkey-register-options:{user.id}", limit=10, window_seconds=300)

    existing = (await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    )).scalars().all()
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        # The 16 raw bytes of the account's own UUID -- stable, unique, and
        # well under the spec's 64-byte user.id limit. Not used to look up
        # the account anywhere (every lookup here goes through credential_id
        # instead), so it doesn't need to be reversible.
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.full_name,
        # Already-registered credentials are excluded so the platform
        # authenticator can offer "this passkey is already set up" instead
        # of silently creating a duplicate for the same device.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    await get_redis().set(
        f"webauthn:register_challenge:{user.id}",
        bytes_to_base64url(options.challenge),
        ex=_WEBAUTHN_CHALLENGE_TTL_SECONDS,
    )
    return Response(content=options_to_json(options), media_type="application/json")


@router.post("/passkeys/register/verify", response_model=PasskeyOut, status_code=201)
async def passkey_register_verify(
    payload: PasskeyRegisterVerifyIn, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(f"passkey-register-verify:{user.id}", limit=10, window_seconds=300)

    challenge_key = f"webauthn:register_challenge:{user.id}"
    challenge_b64 = await get_redis().get(challenge_key)
    if not challenge_b64:
        raise ValidationAppError(
            "Your passkey setup session expired. Please try again.", code="passkey_challenge_expired"
        )
    await get_redis().delete(challenge_key)  # single-use, regardless of outcome below

    try:
        verification = verify_registration_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
        )
    except WebAuthnException as exc:
        raise ValidationAppError(
            "Could not verify that passkey. Please try again.", code="passkey_verification_failed"
        ) from exc

    credential_id = bytes_to_base64url(verification.credential_id)
    duplicate = (await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.credential_id == credential_id)
    )).scalar_one_or_none()
    if duplicate is not None:
        raise ConflictError("This passkey is already registered.")

    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        device_label=payload.device_label,
    )
    db.add(credential)
    await record_audit_event(
        db, actor_id=user.id, action="user.passkey_registered", resource_type="webauthn_credential",
        ip_address=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(credential)
    return credential


@router.get("/passkeys", response_model=list[PasskeyOut])
async def list_passkeys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id).order_by(WebAuthnCredential.created_at)
    )
    return result.scalars().all()


@router.delete("/passkeys/{passkey_id}", response_model=MessageResponse)
async def delete_passkey(
    passkey_id: uuid.UUID, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.id == passkey_id, WebAuthnCredential.user_id == user.id)
    )
    credential = result.scalar_one_or_none()
    # 404, not 403, whether the row belongs to someone else or doesn't exist
    # at all -- matches this codebase's existing IDOR-avoidance pattern
    # elsewhere (e.g. per-owner lookups in files.py), which never reveals
    # that a resource id exists for an account that isn't the caller's own.
    if credential is None:
        raise NotFoundError("Passkey not found.")

    await db.delete(credential)
    await record_audit_event(
        db, actor_id=user.id, action="user.passkey_removed", resource_type="webauthn_credential",
        resource_id=str(passkey_id), ip_address=get_client_ip(request),
    )
    await db.commit()
    return MessageResponse(message="Passkey removed.")


@router.post("/passkeys/login/options")
async def passkey_login_options(payload: PasskeyLoginOptionsIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Step 1 of signing in with a passkey instead of a password -- no
    existing session, this is an alternative to POST /auth/login. Rate
    limited the same way login() is, by IP and by email."""
    await enforce_rate_limit(f"passkey-login:{get_client_ip(request)}", limit=settings.RATE_LIMIT_LOGIN_PER_5MIN, window_seconds=300)
    await enforce_rate_limit(f"passkey-login-email:{payload.email.lower()}", limit=settings.RATE_LIMIT_LOGIN_PER_5MIN, window_seconds=300)

    email = payload.email.lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    allow_credentials: list[PublicKeyCredentialDescriptor] = []
    if user is not None:
        creds = (await db.execute(
            select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
        )).scalars().all()
        allow_credentials = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in creds]

    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    # Keyed by email rather than a user id, since the caller isn't
    # authenticated yet -- an unknown email still gets a real challenge
    # stashed (with an empty allowCredentials list) so /passkeys/login/verify
    # behaves identically whether or not the account exists, beyond the
    # allowCredentials length itself, which WebAuthn's own mechanics can't hide.
    await get_redis().set(
        f"webauthn:login_challenge:{email}", bytes_to_base64url(options.challenge), ex=_WEBAUTHN_CHALLENGE_TTL_SECONDS
    )
    return Response(content=options_to_json(options), media_type="application/json")


@router.post("/passkeys/login/verify", response_model=TokenResponse)
async def passkey_login_verify(payload: PasskeyLoginVerifyIn, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"passkey-login:{get_client_ip(request)}", limit=settings.RATE_LIMIT_LOGIN_PER_5MIN, window_seconds=300)
    email = payload.email.lower()
    await enforce_rate_limit(f"passkey-login-email:{email}", limit=settings.RATE_LIMIT_LOGIN_PER_5MIN, window_seconds=300)

    generic_error = AuthenticationError("Passkey sign-in failed. Please try again.", code="passkey_login_failed")

    challenge_key = f"webauthn:login_challenge:{email}"
    challenge_b64 = await get_redis().get(challenge_key)
    if not challenge_b64:
        raise generic_error
    await get_redis().delete(challenge_key)  # single-use, regardless of outcome below

    result = await db.execute(
        select(User).where(User.email == email)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()
    credential_id = payload.credential.get("id") if isinstance(payload.credential, dict) else None
    if user is None or not credential_id:
        raise generic_error

    cred_result = await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == credential_id, WebAuthnCredential.user_id == user.id
        )
    )
    credential = cred_result.scalar_one_or_none()
    if credential is None:
        raise generic_error

    try:
        verification = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=credential.public_key,
            credential_current_sign_count=credential.sign_count,
        )
    except WebAuthnException as exc:
        # Clone detection (WebAuthn spec section 6.1.1) happens INSIDE
        # verify_authentication_response itself, as part of the same check
        # that already verified the signature -- a sign count can only be
        # trusted once the assertion carrying it is known to be genuine, so
        # the library folds "count did not increase" into this same
        # exception rather than exposing it as a separate return value. It
        # only enforces this once at least one side of the comparison is
        # nonzero, so authenticators that never increment their counter
        # (Touch ID, Windows Hello -- both commonly stay at 0 forever)
        # aren't permanently locked out after their first use. Re-raising
        # the specific case as passkey_clone_detected (rather than the
        # generic passkey_login_failed every other verification failure
        # gets) lets the frontend point the user at removing the passkey.
        if "sign count" in str(exc).lower():
            await record_audit_event(
                db, actor_id=user.id, action="user.passkey_clone_suspected", resource_type="webauthn_credential",
                resource_id=str(credential.id), result="failure", ip_address=get_client_ip(request),
            )
            await db.commit()
            raise AuthenticationError(
                "This passkey may have been cloned. Sign in with your password instead and remove it from Settings.",
                code="passkey_clone_detected",
            ) from exc
        raise generic_error from exc

    if not user.is_active or user.deleted_at is not None:
        # Same generic error as any other verification failure, not a
        # distinct "Account is disabled." -- mirrors the fix already applied
        # to the password login() path above (see its comment): a disabled
        # account confirming a passkey assertion is genuine is still an
        # oracle an attacker with access to that credential shouldn't get.
        await record_audit_event(
            db, actor_id=user.id, action="user.login_blocked_disabled", resource_type="user",
            resource_id=str(user.id), result="failure", ip_address=get_client_ip(request),
        )
        await db.commit()
        raise generic_error

    credential.sign_count = verification.new_sign_count
    credential.last_used_at = datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)

    is_new_device = not await _is_known_device(db, user.id, request)
    tokens = await _issue_tokens(db, user, request, payload.device_label)
    await record_audit_event(
        db, actor_id=user.id, action="user.login_passkey", resource_type="user",
        resource_id=str(user.id), ip_address=get_client_ip(request),
    )
    await track_event(db, event_type="login", user_id=user.id, source="web")
    await db.commit()

    # Best-effort post-login alert, new devices only -- see the matching
    # note on the password login path above.
    if is_new_device:
        try:
            await notify_security_event(
                db, user, "login_alert", "New sign-in to your account",
                device_label=payload.device_label, ip_address=get_client_ip(request),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("login_alert_notify_failed", user_id=str(user.id))
    return tokens
