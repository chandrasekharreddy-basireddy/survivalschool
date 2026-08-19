from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from app.database import get_db
from app.models.lms import Course
from app.models.user import Role, User
from app.models.user import Session as SessionModel
from app.security.tokens import decode_access_token

settings = get_settings()


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid access token.") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type.")

    user_id = payload.get("sub")
    session_id = payload.get("sid")
    if not user_id or not session_id:
        raise AuthenticationError("Malformed token payload.")

    # Session must still be active — logout-all-sessions revokes here, invalidating
    # every access token tied to that session even before its JWT exp elapses.
    session_row = await db.get(SessionModel, uuid.UUID(session_id))
    if session_row is None or session_row.revoked_at is not None:
        raise AuthenticationError("Session has been revoked. Please log in again.")

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id)).options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthenticationError("Account is not active.")

    request.state.user_id = user.id
    return user


async def get_current_verified_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_email_verified:
        raise AuthorizationError("Email verification required.", code="email_not_verified")
    return user


async def get_current_user_optional(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Same checks as get_current_user, but returns None instead of raising
    when there's no (or an invalid) token — for endpoints that serve public
    content to anonymous callers but still need to know who's asking when
    someone IS logged in (e.g. GET /files/{id}, where a public file is
    visible to anyone but a private one still needs an owner check)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return await get_current_user(request, authorization, db)
    except AuthenticationError:
        return None


def require_permission(*permission_codes: str):
    """Backend-enforced authorization. Every protected endpoint declares the
    permission(s) it needs; the frontend hiding a button is never sufficient
    (spec section 9)."""

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.has_role("SUPER_ADMIN"):
            return user
        if not any(user.has_permission(code) for code in permission_codes):
            raise AuthorizationError(
                f"Missing required permission: {' or '.join(permission_codes)}"
            )
        return user

    return _dependency


def require_role(*role_names: str):
    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.has_role("SUPER_ADMIN"):
            return user
        if not any(user.has_role(r) for r in role_names):
            raise AuthorizationError(f"Requires one of roles: {', '.join(role_names)}")
        return user

    return _dependency


def get_client_ip(request: Request) -> str | None:
    """Resolve the caller's IP for rate limiting and audit logs.

    X-Forwarded-For is attacker-controlled input on any request that reaches
    this app directly (not through a trusted proxy) — trusting it
    unconditionally would let a client mint a fresh rate-limit bucket per
    request just by changing the header, and would let them write whatever
    they want into the audit trail's ip_address field. Only read it when
    TRUST_PROXY_HEADERS is explicitly enabled for this deployment (i.e. you
    know a reverse proxy sits in front of the app and sets/overwrites this
    header itself); otherwise always use the raw TCP peer address, which the
    client cannot spoof.
    """
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # The proxy appends the real client IP as the first hop; anything
            # after it may have been set by the client before reaching the
            # proxy and should not be trusted either, but the leftmost value
            # is what a standard single reverse-proxy setup (nginx-ingress,
            # an ALB, etc.) is expected to have set correctly.
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def require_course_ownership(db: AsyncSession, user: User, course_id: uuid.UUID) -> Course:
    """Shared ownership gate for course-scoped write endpoints (creating or
    publishing an exam/quiz/question/lesson/section/schedule under a course,
    etc.).

    Having e.g. the exam.manage permission — granted broadly to the whole
    INSTRUCTOR role — is not enough on its own: without this check, ANY
    instructor could create or publish content under ANY OTHER instructor's
    course, a real cross-tenant IDOR (this exact bug class was already found
    and fixed once for courses.py's own update/publish endpoints; this
    generalizes that fix so every other course-scoped router shares it
    instead of re-implementing — or missing — the same check).

    course.instructor_id is nullable (an instructor's account can be
    GDPR-deleted while their courses remain, via ON DELETE SET NULL) — an
    ownerless course can only be managed by system.manage, never "matched"
    by coincidence against a None comparison.
    """
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    is_owner = course.instructor_id is not None and course.instructor_id == user.id
    if not is_owner and not user.has_permission("system.manage"):
        raise AuthorizationError("You can only manage your own courses.")
    return course
