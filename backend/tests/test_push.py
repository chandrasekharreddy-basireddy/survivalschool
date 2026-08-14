from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_vapid_public_key_endpoint_reports_configured(client):
    # This deployment's real .env has a real (self-generated) VAPID keypair
    # — assert against whatever the running app's settings actually resolve
    # to, not a hardcoded assumption.
    from app.config import get_settings

    settings = get_settings()
    resp = await client.get("/notifications/push/vapid-public-key")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] == bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)
    if body["configured"]:
        assert body["public_key"] == settings.VAPID_PUBLIC_KEY
    else:
        assert body["public_key"] is None


async def test_subscribe_requires_auth(client):
    resp = await client.post(
        "/notifications/push/subscribe",
        json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "x", "auth": "y"}},
    )
    assert resp.status_code == 401


async def test_subscribe_and_unsubscribe_roundtrip(client):
    _, headers = await auth_headers(client)
    endpoint = "https://fcm.googleapis.com/fcm/send/test-endpoint-roundtrip"

    resp = await client.post(
        "/notifications/push/subscribe",
        headers=headers,
        json={"endpoint": endpoint, "keys": {"p256dh": "p256dh-value", "auth": "auth-value"}, "user_agent": "pytest-agent"},
    )
    assert resp.status_code in (201, 400)  # 400 only if VAPID isn't configured in this env
    if resp.status_code == 400:
        pytest.skip("VAPID not configured in this test environment")

    # Re-subscribing the same endpoint upserts rather than erroring/duplicating.
    resp2 = await client.post(
        "/notifications/push/subscribe",
        headers=headers,
        json={"endpoint": endpoint, "keys": {"p256dh": "new-p256dh", "auth": "new-auth"}},
    )
    assert resp2.status_code == 201

    resp3 = await client.post("/notifications/push/unsubscribe", headers=headers, json={"endpoint": endpoint})
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "unsubscribed"

    # Unsubscribing again (already gone) is idempotent, not an error.
    resp4 = await client.post("/notifications/push/unsubscribe", headers=headers, json={"endpoint": endpoint})
    assert resp4.status_code == 200
    assert resp4.json()["status"] == "not_found"


async def test_preferences_expose_push_enabled_toggle(client):
    _, headers = await auth_headers(client)
    resp = await client.get("/notifications/preferences", headers=headers)
    assert resp.status_code == 200
    assert "push_enabled" in resp.json()
    assert resp.json()["push_enabled"] is True

    resp2 = await client.patch("/notifications/preferences", headers=headers, json={"push_enabled": False})
    assert resp2.status_code == 200
    assert resp2.json()["push_enabled"] is False


async def test_test_push_endpoint_calls_real_webpush_with_correct_vapid_claims(client):
    """Proves the send path is wired correctly end to end — subscription
    stored via the real API, then /push/test triggers notification_service's
    real call chain into push_service.send_to_user -> pywebpush.webpush.
    We mock only the actual network call to the browser push service (which
    doesn't exist for a fake test endpoint) and assert it was invoked with
    this deployment's real VAPID private key and a correctly-shaped
    subscription_info — i.e. everything up to the literal HTTPS POST is
    real, not mocked."""
    email, headers = await auth_headers(client)
    from app.config import get_settings

    settings = get_settings()
    if not (settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY):
        pytest.skip("VAPID not configured in this test environment")

    endpoint = f"https://fcm.googleapis.com/fcm/send/test-{email}"
    resp = await client.post(
        "/notifications/push/subscribe",
        headers=headers,
        json={"endpoint": endpoint, "keys": {"p256dh": "p256dh-value", "auth": "auth-value"}},
    )
    assert resp.status_code == 201

    with patch("app.services.push_service.webpush") as mock_webpush:
        mock_webpush.return_value = None
        resp2 = await client.post("/notifications/push/test", headers=headers)

    assert resp2.status_code == 200
    assert resp2.json()["sent"] == 1
    assert mock_webpush.called
    _, kwargs = mock_webpush.call_args
    assert kwargs["subscription_info"]["endpoint"] == endpoint
    assert kwargs["subscription_info"]["keys"] == {"p256dh": "p256dh-value", "auth": "auth-value"}
    assert kwargs["vapid_private_key"] == settings.VAPID_PRIVATE_KEY
    assert kwargs["vapid_claims"]["sub"] == settings.VAPID_SUBJECT
    import json as _json

    payload = _json.loads(kwargs["data"])
    assert payload["title"] == "Test notification"

    await client.post("/notifications/push/unsubscribe", headers=headers, json={"endpoint": endpoint})


async def test_dead_subscription_is_pruned_on_410_gone(client):
    """A push service returning 410 Gone means the subscription is
    permanently dead (user revoked permission, browser data cleared) — the
    real production behavior is to delete it so we stop trying forever."""
    from pywebpush import WebPushException

    email, headers = await auth_headers(client)
    from app.config import get_settings

    settings = get_settings()
    if not (settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY):
        pytest.skip("VAPID not configured in this test environment")

    endpoint = f"https://fcm.googleapis.com/fcm/send/dead-{email}"
    resp = await client.post(
        "/notifications/push/subscribe",
        headers=headers,
        json={"endpoint": endpoint, "keys": {"p256dh": "p256dh-value", "auth": "auth-value"}},
    )
    assert resp.status_code == 201

    class _FakeResponse:
        status_code = 410

    with patch("app.services.push_service.webpush") as mock_webpush:
        mock_webpush.side_effect = WebPushException("Gone", response=_FakeResponse())
        resp2 = await client.post("/notifications/push/test", headers=headers)

    assert resp2.status_code == 200
    assert resp2.json()["sent"] == 0

    # Prune should have actually deleted the row — re-sending finds nothing.
    with patch("app.services.push_service.webpush") as mock_webpush2:
        resp3 = await client.post("/notifications/push/test", headers=headers)
    assert resp3.json()["sent"] == 0
    assert not mock_webpush2.called
