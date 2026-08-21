"""Regression coverage for a second, distinct production failure mode in
SarvamAIProvider.chat(): even after fixing the max_tokens truncation bug
(see test_ai_question_generation.py), a completely benign request ("OOP" /
"python" — nothing content-filter-worthy about it) still failed in
production with "Sarvam returned empty message content." minutes after
that fix deployed. With no documented cause and no way to reproduce it
against the real API from here, the pragmatic mitigation is one retry of
the identical request before giving up — this covers that retry loop
directly, mocking httpx itself rather than chat() (which the other AI
test files monkeypatch wholesale, testing chat()'s own callers instead)."""
from __future__ import annotations

import httpx
import pytest

from app.services.ai_provider import SarvamAIProvider

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _no_real_delay(monkeypatch):
    # The retry loop sleeps between attempts — patch it out so this test
    # file doesn't actually wait on the real delay.
    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr("app.services.ai_provider.asyncio.sleep", _instant_sleep)


def _provider() -> SarvamAIProvider:
    provider = SarvamAIProvider()
    provider.api_key = "fake-key-for-test"
    return provider


def _json_response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://example.test"))


async def test_chat_retries_once_on_empty_content_then_succeeds(monkeypatch):
    provider = _provider()
    calls = []

    async def fake_post(self, url, headers=None, json=None):
        calls.append(json)
        if len(calls) == 1:
            return _json_response(200, {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]})
        return _json_response(200, {"choices": [{"message": {"content": "real answer"}}], "usage": {"total_tokens": 5}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = await provider.chat([{"role": "user", "content": "hi"}])

    assert resp.error is None
    assert resp.content == "real answer"
    assert len(calls) == 2  # confirms a retry actually happened, not a fluke first-try success


async def test_chat_gives_up_after_exhausting_retries_on_empty_content(monkeypatch):
    provider = _provider()
    calls = []

    async def fake_post(self, url, headers=None, json=None):
        calls.append(json)
        return _json_response(200, {"choices": [{"message": {"content": "   "}, "finish_reason": "stop"}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = await provider.chat([{"role": "user", "content": "hi"}])

    assert resp.error == "Sarvam returned empty message content."
    assert len(calls) == 2  # bounded, not unbounded retrying


async def test_chat_does_not_retry_a_definite_4xx(monkeypatch):
    """A 4xx is far more likely to fail identically on retry (bad request,
    auth, rate limit) — retrying it just wastes time and quota. Only the
    empty-content shape gets retried."""
    provider = _provider()
    calls = []

    async def fake_post(self, url, headers=None, json=None):
        calls.append(json)
        return httpx.Response(400, text="bad request", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = await provider.chat([{"role": "user", "content": "hi"}])

    assert len(calls) == 1
    assert resp.error is not None and "400" in resp.error


async def test_chat_retries_on_a_transient_network_exception(monkeypatch):
    provider = _provider()
    calls = []

    async def fake_post(self, url, headers=None, json=None):
        calls.append(json)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("connection timed out")
        return _json_response(200, {"choices": [{"message": {"content": "recovered"}}], "usage": {"total_tokens": 3}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = await provider.chat([{"role": "user", "content": "hi"}])

    assert resp.error is None
    assert resp.content == "recovered"
    assert len(calls) == 2
