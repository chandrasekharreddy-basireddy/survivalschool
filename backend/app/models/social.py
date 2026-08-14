from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk

# ---- Chat ----


class ChatRoom(Base, UUIDPk, Timestamped):
    __tablename__ = "chat_rooms"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    room_type: Mapped[str] = mapped_column(String(20), nullable=False)  # direct|course|announcement
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ChatMember(Base, UUIDPk, Timestamped):
    __tablename__ = "chat_members"

    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)  # member|moderator
    muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ChatMessage(Base, UUIDPk, Timestamped):
    __tablename__ = "chat_messages"

    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MessageRead(Base, UUIDPk, Timestamped):
    __tablename__ = "message_reads"

    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


# ---- Notifications ----


class Notification(Base, UUIDPk, Timestamped):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # course|assessment|achievement|announcement|ai|security
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    link_url: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class NotificationPreference(Base, UUIDPk, Timestamped):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    course_updates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assessment_updates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    achievement_updates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    announcements: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # security_notifications intentionally has NO column here — security notifications
    # (login alerts, password changes) cannot be disabled; enforced in notification_service.py.
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PushSubscription(Base, UUIDPk, Timestamped):
    """A single browser/device Web Push subscription (RFC 8030), as returned by
    `PushManager.subscribe()` in the browser. One user can have several (phone,
    laptop, a second browser) — each is delivered to independently.

    No third-party push provider account is involved: the `endpoint` is the
    browser vendor's own push service (Chrome -> Google's FCM endpoint,
    Firefox -> Mozilla's autopush, Edge -> Microsoft's), reached directly by
    the backend using this app's own self-generated VAPID keypair
    (see app/services/push_service.py) — nothing beyond what the open Web
    Push standard requires.
    """

    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))
