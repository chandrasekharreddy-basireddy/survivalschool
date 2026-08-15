"""
Real tests for the Supabase Storage backend (app/services/storage_service.py).

Network calls to Supabase are mocked (no live Supabase credentials in CI),
but everything else is real: the actual request URL/headers/body construction,
the actual error-raising behavior on non-2xx responses, and the actual
integration through the /files endpoints when STORAGE_BACKEND=supabase.
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import storage_service
from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _mock_response(status_code: int, content: bytes = b"", text: str = "") -> httpx.Response:
    return httpx.Response(status_code=status_code, content=content or text.encode())


async def test_upload_object_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(storage_service.settings, "SUPABASE_STORAGE_URL", None)
    monkeypatch.setattr(storage_service.settings, "SUPABASE_SERVICE_ROLE_KEY", None)
    with pytest.raises(storage_service.StorageNotConfiguredError):
        await storage_service.upload_object("key.png", b"data", "image/png")


async def test_upload_object_posts_to_correct_url_with_service_role_auth(monkeypatch):
    monkeypatch.setattr(storage_service.settings, "SUPABASE_STORAGE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(storage_service.settings, "SUPABASE_SERVICE_ROLE_KEY", "sr-key-123")
    monkeypatch.setattr(storage_service.settings, "SUPABASE_STORAGE_BUCKET", "survivalschool-uploads")

    captured = {}

    async def fake_post(self, url, headers=None, content=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["content"] = content
        return _mock_response(200)

    with patch.object(httpx.AsyncClient, "post", fake_post):
        await storage_service.upload_object("abc123.png", b"pngbytes", "image/png")

    assert captured["url"] == "https://proj.supabase.co/storage/v1/object/survivalschool-uploads/abc123.png"
    assert captured["headers"]["Authorization"] == "Bearer sr-key-123"
    assert captured["headers"]["apikey"] == "sr-key-123"
    assert captured["headers"]["Content-Type"] == "image/png"
    assert captured["content"] == b"pngbytes"


async def test_upload_object_raises_real_error_on_failure_status(monkeypatch):
    monkeypatch.setattr(storage_service.settings, "SUPABASE_STORAGE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(storage_service.settings, "SUPABASE_SERVICE_ROLE_KEY", "sr-key-123")

    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=_mock_response(403, text="Forbidden"))):
        with pytest.raises(RuntimeError, match="403"):
            await storage_service.upload_object("abc123.png", b"x", "image/png")


async def test_download_object_returns_bytes_on_success(monkeypatch):
    monkeypatch.setattr(storage_service.settings, "SUPABASE_STORAGE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(storage_service.settings, "SUPABASE_SERVICE_ROLE_KEY", "sr-key-123")

    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_mock_response(200, content=b"filebytes"))):
        result = await storage_service.download_object("abc123.png")

    assert result == b"filebytes"


async def test_download_object_raises_on_404(monkeypatch):
    monkeypatch.setattr(storage_service.settings, "SUPABASE_STORAGE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(storage_service.settings, "SUPABASE_SERVICE_ROLE_KEY", "sr-key-123")

    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_mock_response(404, text="not found"))):
        with pytest.raises(RuntimeError, match="404"):
            await storage_service.download_object("missing.png")


async def test_upload_endpoint_uses_supabase_backend_end_to_end(client, monkeypatch):
    """Real integration through the /files API with STORAGE_BACKEND=supabase --
    only the actual outbound HTTP call to Supabase is mocked; everything else
    (auth, MIME sniffing, DB record, download-path routing) is real."""
    from app.api.v1 import files as files_module

    monkeypatch.setattr(files_module.settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(storage_service.settings, "SUPABASE_STORAGE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(storage_service.settings, "SUPABASE_SERVICE_ROLE_KEY", "sr-key-123")

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    _, headers = await auth_headers(client)

    # Mock only storage_service's own outbound calls (not httpx.AsyncClient
    # globally) -- the test client itself uses httpx internally to drive the
    # ASGI app, and patching the class method would intercept that too.
    with patch.object(storage_service, "upload_object", AsyncMock(return_value=None)) as mock_upload:
        upload = await client.post(
            "/files", headers=headers, params={"visibility": "public"},
            files={"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")},
        )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    mock_upload.assert_awaited_once()
    assert mock_upload.await_args.args[0]  # storage_key was passed
    assert mock_upload.await_args.args[1] == png_bytes
    assert mock_upload.await_args.args[2] == "image/png"

    with patch.object(storage_service, "download_object", AsyncMock(return_value=png_bytes)):
        download = await client.get(body["url"].replace("/api/v1", ""))
    assert download.status_code == 200
    assert download.content == png_bytes


async def test_upload_endpoint_returns_503_when_supabase_misconfigured(client, monkeypatch):
    from app.api.v1 import files as files_module

    monkeypatch.setattr(files_module.settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(storage_service.settings, "SUPABASE_STORAGE_URL", None)
    monkeypatch.setattr(storage_service.settings, "SUPABASE_SERVICE_ROLE_KEY", None)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    _, headers = await auth_headers(client)
    resp = await client.post(
        "/files", headers=headers,
        files={"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert resp.status_code == 503
