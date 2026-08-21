from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class Role(Base, UUIDPk, Timestamped):
    """STUDENT, INSTRUCTOR, MODERATOR, SUPPORT, ADMIN, SUPER_ADMIN."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255))

    permissions: Mapped[list[Permission]] = relationship(
        secondary="role_permissions", back_populates="roles"
    )


class Permission(Base, UUIDPk, Timestamped):
    """e.g. courses.create, quiz.manage, analytics.view — see docs/SECURITY.md."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list[Role]] = relationship(secondary="role_permissions", back_populates="permissions")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class User(Base, UUIDPk, Timestamped):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(email) > 3", name="ck_users_email_len"),
    )

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Real TOTP 2FA (RFC 6238) — see services/totp_service.py for the full
    # design rationale (TOTP over SMS, why the secret is "pending" until
    # confirmed, why backup codes are hashed). totp_secret is written at
    # setup time but totp_enabled only flips to True once the user proves
    # their authenticator app actually has it, in POST /auth/2fa/confirm.
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_backup_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)  # SHA-256 hashes only

    roles: Mapped[list[Role]] = relationship(secondary="user_roles")
    # passive_deletes=True: trust the DB's own ON DELETE CASCADE on
    # profiles.user_id (verified via pg_constraint — see
    # app/services/gdpr_service.py's module docstring) rather than letting
    # SQLAlchemy's unit-of-work try to manage the child row itself. Without
    # this, deleting a User with an ORM-loaded `profile` relationship emits
    # `UPDATE profiles SET user_id = NULL ...` before the DELETE (the
    # default "disassociate the child" behavior for a nullable-looking
    # one-to-one), which fails outright since profiles.user_id is NOT NULL
    # — breaking real account deletion for any user who has ever loaded
    # their profile (e.g. via GET /users/me/profile).
    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False, passive_deletes=True)

    def has_permission(self, code: str) -> bool:
        return any(p.code == code for r in self.roles for p in r.permissions)

    def has_role(self, name: str) -> bool:
        return any(r.name == name for r in self.roles)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class Profile(Base, UUIDPk, Timestamped):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("public_handle", name="uq_profiles_public_handle"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # The shareable "@handle" other students find/invite by (elimination
    # battles, follow search) instead of exposing email. Nullable until the
    # student sets one (see users.py's handle-claim endpoint); existing
    # accounts backfill lazily rather than a forced migration prompt.
    public_handle: Mapped[str | None] = mapped_column(String(30))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(String(1000))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    locale: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    # Which school (SCDS, SOAI, SOB, ...) the student's section below
    # belongs to — section numbers repeat across schools (see
    # campus_timetable_service.py's row_key comment: "group identity is
    # school + section"), so section alone can't disambiguate a student's
    # actual schedule once more than one school is in the uploaded
    # timetable. Nullable/optional so existing accounts that only ever set
    # section keep working exactly as before (my_campus_entries falls back
    # to matching on section alone when school is unset).
    school: Mapped[str | None] = mapped_column(String(120))
    # Free-text campus section/roll group (e.g. "A", "CSE-3B") — set once by
    # the student, picked from GET /timetable/campus/sections' real options
    # rather than typed blind, so GET /timetable/campus/me can filter the
    # university-wide schedule down to just their own classes.
    section: Mapped[str | None] = mapped_column(String(60))
    # Optional, free-text — shown/editable at AI Weekly Exam registration so
    # it only has to be typed once and is auto-filled on every later visit.
    institute: Mapped[str | None] = mapped_column(String(150))

    user: Mapped[User] = relationship(back_populates="profile")


class EmailVerification(Base, UUIDPk, Timestamped):
    __tablename__ = "email_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base, UUIDPk, Timestamped):
    __tablename__ = "password_resets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base, UUIDPk, Timestamped):
    """Refresh tokens are never stored raw — only a SHA-256 hash, per SECURITY.md."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_refresh_token_hash"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Points at the token that superseded this one during rotation. Without a
    # real FK the column can outlive its target (the cleanup job deletes expired
    # tokens) and silently dangle; SET NULL keeps the audit trail honest.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )


class Session(Base, UUIDPk, Timestamped):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_label: Mapped[str | None] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstructorApplication(Base, UUIDPk, Timestamped):
    """Deliberately NOT self-service role assignment: applying creates this
    row in `pending` state, and only an admin approving it (which grants the
    INSTRUCTOR role through the normal, already-audited
    POST /users/{id}/roles/{role} path) actually changes what the applicant
    can do. Letting registration directly grant INSTRUCTOR would reopen the
    same class of cross-tenant privilege-escalation bug already closed for
    course ownership elsewhere in this codebase.

    Also deliberately NOT gated by the Thursday student registration window
    (see registration_service.py) — that window controls admission to the
    weekly student exam cohort specifically; it has nothing to do with
    instructors, who don't sit in that cohort.
    """
    __tablename__ = "instructor_applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|approved|rejected
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(1000))

    user: Mapped[User] = relationship(foreign_keys=[user_id])
