"""Regression test for a real production bug: every single n8n webhook
call has been failing with 403 Forbidden since this integration was first
wired up (confirmed in production logs going back days). The n8n webhook
trigger enforces header auth on a header literally named "X-Webhook-Secret"
(its own Header Auth credential's configured header name) — emit_event was
sending a completely different header name ("x-n8n-webhook-secret"), which
n8n correctly rejects since the header it checks for is simply never
present."""
from __future__ import annotations

import httpx
import pytest

import app.services.n8n_service as n8n_service

pytestmark = pytest.mark.asyncio


async def test_emit_event_sends_the_exact_header_name_n8n_expects(monkeypatch):
    monkeypatch.setattr(n8n_service.settings, "N8N_WEBHOOK_BASE_URL", "https://example-n8n.test")
    monkeypatch.setattr(n8n_service.settings, "N8N_WEBHOOK_SECRET", "test-secret-value")
    captured = {}

    async def fake_post(self, url, json=None, headers=None):
        captured["headers"] = headers
        captured["url"] = url
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await n8n_service.emit_event("student.registered", {"email": "a@example.com"})

    # The exact header name n8n's Header Auth credential checks for —
    # HTTP header names are case-insensitive, but this must be the same
    # NAME, not a different name entirely (the actual bug: "x-n8n-webhook-
    # secret" vs "X-Webhook-Secret" are two different headers).
    assert captured["headers"]["X-Webhook-Secret"] == "test-secret-value"
    assert captured["url"] == "https://example-n8n.test/webhook/survivalschool/events"


async def test_emit_event_is_a_silent_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(n8n_service.settings, "N8N_WEBHOOK_BASE_URL", "")
    calls = []
    monkeypatch.setattr(httpx.AsyncClient, "post", lambda *a, **k: calls.append(1))
    await n8n_service.emit_event("student.registered", {"email": "a@example.com"})
    assert calls == []


async def test_emit_event_never_raises_when_n8n_is_unreachable(monkeypatch):
    """The whole point of this integration being fire-and-forget: an n8n
    outage must never fail the request that triggered the event."""
    monkeypatch.setattr(n8n_service.settings, "N8N_WEBHOOK_BASE_URL", "https://example-n8n.test")
    monkeypatch.setattr(n8n_service.settings, "N8N_WEBHOOK_SECRET", "test-secret-value")

    async def fake_post(self, url, json=None, headers=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await n8n_service.emit_event("student.registered", {"email": "a@example.com"})  # must not raise
