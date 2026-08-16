from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AppError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.social import Notification, NotificationPreference
from app.models.user import User
from app.services.push_service import push_configured, remove_subscription, save_subscription, send_to_user

router = APIRouter(prefix="/notifications", tags=["notifications"])
settings = get_settings()


class NotificationOut(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    body: str
    link_url: str | None
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PreferencesUpdate(BaseModel):
    course_updates: bool | None = None
    assessment_updates: bool | None = None
    achievement_updates: bool | None = None
    announcements: bool | None = None
    ai_notifications: bool | None = None
    email_enabled: bool | None = None
    push_enabled: bool | None = None


class PreferencesOut(BaseModel):
    course_updates: bool
    assessment_updates: bool
    achievement_updates: bool
    announcements: bool
    ai_notifications: bool
    email_enabled: bool
    push_enabled: bool

    model_config = {"from_attributes": True}


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeIn(BaseModel):
    endpoint: str
    keys: PushKeys
    user_agent: str | None = None


class PushSubscribeOut(BaseModel):
    status: str


class PushUnsubscribeIn(BaseModel):
    endpoint: str


class VapidPublicKeyOut(BaseModel):
    configured: bool
    public_key: str | None = None


@router.get("", response_model=list[NotificationOut])
async def list_notifications(unread_only: bool = Query(False), limit: int = Query(30, le=100),
                              user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    result = await db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit))
    return result.scalars().all()


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(notification_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    notif = await db.get(Notification, notification_id)
    if notif is None or notif.user_id != user.id:
        raise NotFoundError("Notification not found.")
    notif.read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notif)
    return notif


@router.get("/preferences", response_model=PreferencesOut)
async def get_preferences(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    prefs = (await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user.id))).scalar_one_or_none()
    if prefs is None:
        prefs = NotificationPreference(user_id=user.id)
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)
    return prefs


@router.patch("/preferences", response_model=PreferencesOut)
async def update_preferences(payload: PreferencesUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    prefs = (await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user.id))).scalar_one_or_none()
    if prefs is None:
        prefs = NotificationPreference(user_id=user.id)
        db.add(prefs)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)
    await db.commit()
    await db.refresh(prefs)
    return prefs


@router.get("/push/vapid-public-key", response_model=VapidPublicKeyOut)
async def get_vapid_public_key():
    """Expose only the public VAPID key; the private key stays server-side."""
    return VapidPublicKeyOut(configured=push_configured(), public_key=settings.VAPID_PUBLIC_KEY if push_configured() else None)


@router.post("/push/subscribe", status_code=201, response_model=PushSubscribeOut)
async def subscribe_push(payload: PushSubscribeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not push_configured():
        raise AppError("Push notifications are not configured on this server.")
    await save_subscription(
        db, user_id=user.id, endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh, auth=payload.keys.auth, user_agent=payload.user_agent,
    )
    await db.commit()
    return PushSubscribeOut(status="subscribed")


@router.post("/push/unsubscribe")
async def unsubscribe_push(payload: PushUnsubscribeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    removed = await remove_subscription(db, user_id=user.id, endpoint=payload.endpoint)
    await db.commit()
    return {"status": "unsubscribed" if removed else "not_found"}


@router.post("/push/test")
async def send_test_push(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not push_configured():
        raise AppError("Push notifications are not configured on this server.")
    sent = await send_to_user(db, user_id=user.id, title="Test notification", body="Push notifications are working.", url="/settings")
    await db.commit()
    return {"sent": sent}
