"""In-app + email notification dispatch, respecting per-category preferences.

Security notifications (login alerts, password changes) are NEVER gated by
preferences — spec section 22: "Security notifications cannot be silently
disabled if they are required for account security."
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.social import Notification, NotificationPreference
from app.models.user import User
from app.services.email_service import send_email

settings = get_settings()

_PREFERENCE_FIELD_BY_CATEGORY = {
    "course": "course_updates",
    "assessment": "assessment_updates",
    "achievement": "achievement_updates",
    "announcement": "announcements",
    "ai": "ai_notifications",
}


async def _get_or_create_prefs(db: AsyncSession, user_id) -> NotificationPreference:
    result = await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    prefs = result.scalar_one_or_none()
    if prefs is None:
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
        await db.flush()
    return prefs


async def create_notification(
    db: AsyncSession,
    *,
    user: User,
    category: str,
    title: str,
    body: str = "",
    link_url: str | None = None,
    metadata: dict | None = None,
    email_template: str | None = None,
    email_context: dict | None = None,
) -> Notification:
    prefs = await _get_or_create_prefs(db, user.id)
    pref_field = _PREFERENCE_FIELD_BY_CATEGORY.get(category)
    allowed = True if category == "security" or pref_field is None else getattr(prefs, pref_field)

    notification = Notification(
        user_id=user.id, category=category, title=title, body=body,
        link_url=link_url, metadata_json=metadata or {},
    )
    db.add(notification)
    await db.flush()

    if allowed and prefs.email_enabled and email_template:
        await send_email(user.email, title, email_template, full_name=user.full_name, **(email_context or {}))
    elif category == "security" and email_template:
        # security emails bypass email_enabled too
        await send_email(user.email, title, email_template, full_name=user.full_name, **(email_context or {}))

    return notification


async def notify_security_event(db: AsyncSession, user: User, template: str, title: str, **context) -> None:
    await create_notification(
        db, user=user, category="security", title=title,
        body="Security event on your account.", email_template=template, email_context=context,
    )
