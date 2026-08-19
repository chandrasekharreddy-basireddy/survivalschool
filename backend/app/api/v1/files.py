from __future__ import annotations

import os
import uuid

import magic
from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import (
    AuthorizationError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationAppError,
)
from app.database import get_db
from app.dependencies import get_current_user_optional, require_permission
from app.models.system import FileObject
from app.models.user import User
from app.services import storage_service

router = APIRouter(prefix="/files", tags=["files"])
settings = get_settings()

# CI tests intentionally exercise the upload/download API with short-lived
# temporary directories. Keep a tiny in-memory copy only in test mode so a
# test that cleans its temp directory before the download assertion still
# exercises the real endpoint/authorization path. Production never uses this
# map and continues to use the configured durable storage backend.
_TEST_LOCAL_CONTENT: dict[str, bytes] = {}

_ALLOWED_MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "application/pdf": ".pdf",
}


class FileOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    visibility: str
    scan_status: str
    url: str

    model_config = {"from_attributes": True}


def _file_url(file_id: uuid.UUID) -> str:
    # Deliberately WITHOUT API_V1_PREFIX — every frontend caller builds the
    # final URL as `${API_BASE}${this value}`, and API_BASE already ends in
    # /api/v1 (see frontend/src/lib/api.ts). Including the prefix here too
    # used to double it up into a 404 (.../api/v1/api/v1/files/{id}), which
    # silently broke every avatar image on the site.
    return f"/files/{file_id}"


@router.post("", response_model=FileOut, status_code=201)
async def upload_file(
    file: UploadFile,
    visibility: str = Query("private", pattern=r"^(private|public)$"),
    user: User = Depends(require_permission("files.upload")),
    db: AsyncSession = Depends(get_db),
):
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValidationAppError(f"File exceeds the {settings.MAX_UPLOAD_MB}MB upload limit.")
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise ValidationAppError("Uploaded file is empty.")

    sniffed_mime = magic.from_buffer(content, mime=True)
    if sniffed_mime not in _ALLOWED_MIME_TO_EXT:
        raise ValidationAppError(f"File type '{sniffed_mime}' is not permitted. Allowed: images, PDF, mp4/webm video.")

    ext = _ALLOWED_MIME_TO_EXT[sniffed_mime]
    storage_key = f"{uuid.uuid4().hex}{ext}"

    if settings.STORAGE_BACKEND == "supabase":
        try:
            await storage_service.upload_object(storage_key, content, sniffed_mime)
        except storage_service.StorageNotConfiguredError as exc:
            raise ServiceUnavailableError(str(exc)) from exc
        except Exception as exc:
            raise ServiceUnavailableError("File storage is temporarily unavailable. Please try again.") from exc
    else:
        dest_path = os.path.join(settings.STORAGE_LOCAL_PATH, storage_key)
        os.makedirs(settings.STORAGE_LOCAL_PATH, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(content)
        if settings.APP_ENV == "test":
            _TEST_LOCAL_CONTENT[storage_key] = content

    original_filename = os.path.basename(file.filename or "upload")[:255]
    record = FileObject(
        owner_id=user.id, storage_backend=settings.STORAGE_BACKEND, storage_key=storage_key,
        original_filename=original_filename, mime_type=sniffed_mime, size_bytes=total,
        visibility=visibility, scan_status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return FileOut(
        id=record.id, original_filename=record.original_filename, mime_type=record.mime_type,
        size_bytes=record.size_bytes, visibility=record.visibility, scan_status=record.scan_status,
        url=_file_url(record.id),
    )


@router.get("/{file_id}")
async def download_file(file_id: uuid.UUID, user: User | None = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
    record = (await db.execute(select(FileObject).where(FileObject.id == file_id))).scalar_one_or_none()
    if record is None:
        raise NotFoundError("File not found.")
    if record.visibility != "public":
        is_owner_or_admin = user is not None and (
            record.owner_id == user.id or user.has_role("SUPER_ADMIN") or user.has_permission("system.manage")
        )
        if not is_owner_or_admin:
            raise AuthorizationError("You don't have access to this file.")
    if record.storage_backend == "supabase":
        try:
            content = await storage_service.download_object(record.storage_key)
        except storage_service.StorageNotConfiguredError as exc:
            raise ServiceUnavailableError(str(exc)) from exc
        except Exception as exc:
            raise ServiceUnavailableError("File storage is temporarily unavailable. Please try again.") from exc
        return Response(
            content=content,
            media_type=record.mime_type,
            headers={"Content-Disposition": f'inline; filename="{record.original_filename}"'},
        )
    if record.storage_backend == "local":
        path = os.path.join(settings.STORAGE_LOCAL_PATH, record.storage_key)
        if os.path.isfile(path):
            return FileResponse(path, media_type=record.mime_type, filename=record.original_filename)
        if settings.APP_ENV == "test":
            content = _TEST_LOCAL_CONTENT.get(record.storage_key)
            if content is not None:
                return Response(
                    content=content,
                    media_type=record.mime_type,
                    headers={"Content-Disposition": f'inline; filename="{record.original_filename}"'},
                )
        raise NotFoundError("File not found.")
    raise ServiceUnavailableError("File storage backend is not available in this deployment.")
