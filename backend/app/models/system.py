from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class AnalyticsEvent(Base, UUIDPk):
    """Append-only event stream, decoupled from transactional tables so Power BI /
    downstream analytics never queries hot OLTP tables directly (spec section 24).
    Deliberately excludes PII beyond user_id.
    """

    __tablename__ = "analytics_events"

    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(30), default="web", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", index=True)


class AuditLog(Base, UUIDPk):
    """Immutable — application code must never UPDATE or DELETE rows here."""

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # Indexed: the admin audit-log search filters directly on resource_type and
    # result, and this table is append-only/unbounded, so unindexed filters on
    # it get steadily worse forever.
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # success|failure
    ip_address: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", index=True)


class SupportTicket(Base, UUIDPk, Timestamped):
    __tablename__ = "support_tickets"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open|in_progress|closed
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class FileObject(Base, UUIDPk, Timestamped):
    __tablename__ = "files"
    # A storage key identifies one physical object in the backend; two rows
    # pointing at the same blob means a delete of one silently breaks the
    # other. Scoped by backend since keys are only unique within one.
    __table_args__ = (UniqueConstraint("storage_backend", "storage_key", name="uq_file_backend_key"),)

    # Indexed as the natural lookup key for a "my files" listing — no such
    # endpoint exists yet, but every other FK-into-users column in this
    # schema is indexed and this one shouldn't start out as the exception.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    storage_backend: Mapped[str] = mapped_column(String(20), nullable=False)  # local|supabase
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False)  # private|public
    scan_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|clean|flagged


class SystemSetting(Base, UUIDPk, Timestamped):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
