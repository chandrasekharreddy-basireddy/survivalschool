"""
Real Supabase Storage backend for durable file uploads.

Render's own web service container disk is ephemeral -- it's wiped on every
redeploy (new build) and can be rescheduled to different hardware at any
time. That's fine for STORAGE_BACKEND=local in dev/CI, but not safe for real
user-uploaded files in production. This module talks to Supabase Storage's
REST API directly (no supabase-py dependency needed -- it's a small,
well-documented HTTP surface) using the service role key, which bypasses
Supabase's Row Level Security. That's the correct model here: this app has
its own JWT-based auth and its own per-file visibility/ownership checks in
app/api/v1/files.py, enforced *before* any call into this module -- we are
not trying to map our own users onto Supabase Auth's RLS model.

All functions raise on failure (network error, non-2xx response) rather than
swallowing errors -- callers decide how to translate that into an HTTP
response for their endpoint.
"""
from __future__ import annotations

import httpx

from app.config import get_settings

settings = get_settings()


class StorageNotConfiguredError(RuntimeError):
    """Raised when STORAGE_BACKEND=supabase but credentials are missing."""


def _require_config() -> tuple[str, str, str]:
    if not (settings.SUPABASE_STORAGE_URL and settings.SUPABASE_SERVICE_ROLE_KEY):
        raise StorageNotConfiguredError(
            "SUPABASE_STORAGE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set "
            "to use STORAGE_BACKEND=supabase."
        )
    base_url = settings.SUPABASE_STORAGE_URL.rstrip("/")
    return base_url, settings.SUPABASE_SERVICE_ROLE_KEY, settings.SUPABASE_STORAGE_BUCKET


def _headers(service_role_key: str, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


async def upload_object(storage_key: str, content: bytes, content_type: str) -> None:
    """Upload bytes to the configured Supabase Storage bucket. Raises on failure."""
    base_url, key, bucket = _require_config()
    url = f"{base_url}/storage/v1/object/{bucket}/{storage_key}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=_headers(key, content_type), content=content)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase Storage upload failed ({resp.status_code}): {resp.text[:300]}")


async def download_object(storage_key: str) -> bytes:
    """Download bytes from the configured Supabase Storage bucket. Raises on failure."""
    base_url, key, bucket = _require_config()
    url = f"{base_url}/storage/v1/object/{bucket}/{storage_key}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=_headers(key))
    if resp.status_code != 200:
        raise RuntimeError(f"Supabase Storage download failed ({resp.status_code}): {resp.text[:300]}")
    return resp.content


async def delete_object(storage_key: str) -> None:
    """Delete an object from the configured Supabase Storage bucket. Raises on failure."""
    base_url, key, bucket = _require_config()
    url = f"{base_url}/storage/v1/object/{bucket}/{storage_key}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(url, headers=_headers(key))
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Supabase Storage delete failed ({resp.status_code}): {resp.text[:300]}")
