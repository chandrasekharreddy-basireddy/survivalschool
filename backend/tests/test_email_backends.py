from __future__ import annotations

import pytest

import app.services.email_service as es

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _FakeResp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """Stands in for httpx.AsyncClient so the Resend backend can be exercised
    end-to-end (payload shape, auth header, error handling) without touching
    the network."""
    captured: list[dict] = []
    next_status = 200
    next_text = '{"id":"abc"}'

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeClient.captured.append({"url": url, "headers": headers, "json": json})
        return _FakeResp(_FakeClient.next_status, _FakeClient.next_text)


async def test_send_resend_posts_correct_payload_over_https(monkeypatch):
    monkeypatch.setattr(es.settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(es.settings, "EMAIL_FROM", "Survival School <no-reply@example.com>")
    _FakeClient.captured = []
    _FakeClient.next_status = 200
    _FakeClient.next_text = '{"id":"abc"}'
    monkeypatch.setattr(es.httpx, "AsyncClient", _FakeClient)

    await es._send_resend(to="student@example.com", subject="Verify your account",
                          html="<b>hi</b>", text="hi")

    assert len(_FakeClient.captured) == 1
    sent = _FakeClient.captured[0]
    # Must be the HTTPS API endpoint (port 443) -- the whole point vs SMTP.
    assert sent["url"] == "https://api.resend.com/emails"
    assert sent["headers"]["Authorization"] == "Bearer re_test_key"
    assert sent["json"]["from"] == "Survival School <no-reply@example.com>"
    assert sent["json"]["to"] == ["student@example.com"]
    assert sent["json"]["html"] == "<b>hi</b>"
    assert sent["json"]["text"] == "hi"


async def test_send_resend_raises_on_non_2xx_with_provider_error(monkeypatch):
    monkeypatch.setattr(es.settings, "RESEND_API_KEY", "re_test_key")
    _FakeClient.captured = []
    _FakeClient.next_status = 403
    _FakeClient.next_text = '{"message":"The domain is not verified."}'
    monkeypatch.setattr(es.httpx, "AsyncClient", _FakeClient)

    # A non-2xx must raise (so the caller logs email_send_failed) and must
    # carry the provider's real error text so the operator knows what to fix.
    with pytest.raises(RuntimeError, match="403.*not verified"):
        await es._send_resend(to="s@example.com", subject="V", html="<b>hi</b>", text="hi")


async def test_send_resend_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(es.settings, "RESEND_API_KEY", None)
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        await es._send_resend(to="s@example.com", subject="V", html="<b>hi</b>", text="hi")


async def test_send_brevo_posts_correct_payload_and_parses_sender(monkeypatch):
    monkeypatch.setattr(es.settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(es.settings, "EMAIL_FROM", "Survival School <sender@gmail.com>")
    _FakeClient.captured = []
    _FakeClient.next_status = 201
    _FakeClient.next_text = '{"messageId":"<abc@brevo>"}'
    monkeypatch.setattr(es.httpx, "AsyncClient", _FakeClient)

    await es._send_brevo(to="student@example.com", subject="Verify your account",
                         html="<b>hi</b>", text="hi")

    sent = _FakeClient.captured[0]
    assert sent["url"] == "https://api.brevo.com/v3/smtp/email"
    assert sent["headers"]["api-key"] == "xkeysib-test"
    # "Name <email>" from EMAIL_FROM must be split into Brevo's sender object.
    assert sent["json"]["sender"] == {"email": "sender@gmail.com", "name": "Survival School"}
    assert sent["json"]["to"] == [{"email": "student@example.com"}]
    assert sent["json"]["htmlContent"] == "<b>hi</b>"
    assert sent["json"]["textContent"] == "hi"


async def test_send_brevo_raises_on_error_with_provider_body(monkeypatch):
    monkeypatch.setattr(es.settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(es.settings, "EMAIL_FROM", "Survival School <sender@gmail.com>")
    _FakeClient.captured = []
    _FakeClient.next_status = 400
    _FakeClient.next_text = '{"code":"invalid_parameter","message":"Sender not valid"}'
    monkeypatch.setattr(es.httpx, "AsyncClient", _FakeClient)

    with pytest.raises(RuntimeError, match="400.*Sender not valid"):
        await es._send_brevo(to="s@example.com", subject="V", html="<b>hi</b>", text="hi")


async def test_send_brevo_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(es.settings, "BREVO_API_KEY", None)
    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        await es._send_brevo(to="s@example.com", subject="V", html="<b>hi</b>", text="hi")
