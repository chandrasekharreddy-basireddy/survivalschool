from __future__ import annotations

import io
import tempfile
from unittest.mock import patch

import pytest

from tests.conftest import auth_headers, grant_role, login

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_admin(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "ADMIN")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_admin_user_management_endpoints(client):
    _, admin_headers = await _make_admin(client)
    student_email, student_headers = await auth_headers(client)

    listed = await client.get("/admin/users", params={"q": student_email}, headers=admin_headers)
    assert listed.status_code == 200
    assert any(u["email"] == student_email for u in listed.json())

    target = next(u for u in listed.json() if u["email"] == student_email)
    deactivated = await client.post(f"/admin/users/{target['id']}/deactivate", headers=admin_headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    # A deactivated user can no longer authenticate against protected endpoints.
    blocked = await client.get("/auth/me", headers=student_headers)
    assert blocked.status_code == 401

    reactivated = await client.post(f"/admin/users/{target['id']}/activate", headers=admin_headers)
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True


async def test_admin_system_health_reports_detail(client):
    _, admin_headers = await _make_admin(client)
    resp = await client.get("/admin/system-health", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] is True
    assert body["redis"] is True
    assert "app_version" in body and "uptime_seconds" in body


async def test_admin_audit_logs_support_filtering(client):
    _, admin_headers = await _make_admin(client)
    resp = await client.get("/admin/audit-logs", params={"action": "user.deactivated", "limit": 5}, headers=admin_headers)
    assert resp.status_code == 200
    for row in resp.json():
        assert row["action"] == "user.deactivated"


async def test_file_upload_rejects_disallowed_type_and_accepts_image(client):
    """Test file upload with mocked storage to avoid /data permission issues."""
    _, headers = await auth_headers(client)

    bad = await client.post(
        "/files", headers=headers,
        files={"file": ("payload.exe", io.BytesIO(b"MZ" + b"\x00" * 50), "application/octet-stream")},
    )
    assert bad.status_code == 422

    # A minimal valid 1x1 PNG.
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('app.api.v1.files.settings.STORAGE_LOCAL_PATH', tmpdir):
            with patch('app.api.v1.files.os.makedirs') as mock_makedirs:
                mock_makedirs.return_value = None
                good = await client.post(
                    "/files", headers=headers, params={"visibility": "public"},
                    files={"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")},
                )

    assert good.status_code == 201, good.text
    body = good.json()
    assert body["mime_type"] == "image/png"

    download = await client.get(body["url"].replace("/api/v1", ""))
    assert download.status_code == 200
    assert download.content == png_bytes


async def test_private_file_is_not_accessible_to_other_users(client):
    """Test private file access control with mocked storage."""
    _, owner_headers = await auth_headers(client)
    _, other_headers = await auth_headers(client)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('app.api.v1.files.settings.STORAGE_LOCAL_PATH', tmpdir):
            with patch('app.api.v1.files.os.makedirs') as mock_makedirs:
                mock_makedirs.return_value = None
                uploaded = await client.post(
                    "/files", headers=owner_headers, params={"visibility": "private"},
                    files={"file": ("private.png", io.BytesIO(png_bytes), "image/png")},
                )
        file_id = uploaded.json()["id"]

        forbidden = await client.get(f"/files/{file_id}", headers=other_headers)
        assert forbidden.status_code == 403

        anon = await client.get(f"/files/{file_id}")
        assert anon.status_code == 403

        allowed = await client.get(f"/files/{file_id}", headers=owner_headers)
        assert allowed.status_code == 200
