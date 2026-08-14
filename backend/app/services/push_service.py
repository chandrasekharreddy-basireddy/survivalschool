"""Real Web Push (RFC 8030) delivery via VAPID (RFC 8292) — no third-party
push provider account (Firebase, APNs, OneSignal) required.

Sending a push works by talking directly to the browser vendor's own push
service (the URL the browser itself picked and put in `subscription.endpoint`
when the frontend called `PushManager.subscribe()` — e.g. an
`fcm.googleapis.com` URL for Chrome, `updates.push.services.mozilla.com` for
Firefox). `pywebpush` encrypts the payload per RFC 8291 (aes128gcm) using the
subscription's own `p256dh`/`auth` keys and signs the request with this app's
self-generated VAPID keypair so the push service can verify which app server
is allowed to push to that subscription.

Deliberately inert when VAPID keys are not configured — same pattern as
Sentry (app/config.py): a real deployment sets real, per-deployment keys via
env vars (generate with backend/scripts/generate_vapid_keys.py); nothing here
is a fabricated credential.
"""
from __future__ import annotations

import json
import logging
import uuid

import structlog
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.social import PushSubscription

logger = structlog.get_logger("survivalschool.push")
settings = get_settings()


def push_configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


async def save_subscription(
    db: AsyncSession, *, user_id: uuid.UUID, endpoint: str, p256dh: str, auth: str, user_agent: str | None
) -> PushSubscription:
    """Upsert by endpoint — a browser calling subscribe() again for the same
    endpoint (e.g. re-granting permission) should update keys, not duplicate."""
    existing = (
        await db.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    ).scalar_one_or_none()
    if existing is not None:
        existing.user_id = user_id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = user_agent
        await db.flush()
        return existing

    sub = PushSubscription(
        user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=user_agent
    )
    db.add(sub)
    await db.flush()
    return sub


async def remove_subscription(db: AsyncSession, *, user_id: uuid.UUID, endpoint: str) -> bool:
    existing = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == endpoint, PushSubscription.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return False
    await db.delete(existing)
    await db.flush()
    return True


def _send_one(subscription: PushSubscription, payload: dict) -> bool:
    """Synchronous — pywebpush uses the `requests` library under the hood, no
    async client exists upstream, so callers run this via a thread (see
    send_to_user below). Returns True on success, False on a dead
    subscription (caller should delete it), raises on other real errors."""
    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            timeout=5,
        )
        return True
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (404, 410):
            # 404 Not Found / 410 Gone — the push service has permanently
            # invalidated this endpoint (user revoked permission, uninstalled
            # the browser profile, etc.). Not an error worth logging loudly.
            return False
        logger.warning("push_send_failed", endpoint=subscription.endpoint[:60], status=status, error=str(exc))
        raise


async def send_to_user(db: AsyncSession, *, user_id: uuid.UUID, title: str, body: str, url: str | None = None) -> int:
    """Send a real push to every subscription this user has. Prunes dead
    (404/410) subscriptions as it goes. Returns count of successful sends.
    No-ops (returns 0) if VAPID isn't configured — callers never need to
    check push_configured() themselves."""
    if not push_configured():
        return 0

    subs = (
        await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).scalars().all()
    if not subs:
        return 0

    import asyncio

    payload = {"title": title, "body": body, "url": url or "/notifications"}
    sent = 0
    for sub in subs:
        try:
            ok = await asyncio.to_thread(_send_one, sub, payload)
            if ok:
                sent += 1
            else:
                await db.delete(sub)
        except Exception:
            # Real transient failure (network, push service outage) — leave
            # the subscription in place, don't fail the caller's request.
            logging.getLogger("survivalschool.push").exception("push delivery error")
    await db.flush()
    return sent
