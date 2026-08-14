from __future__ import annotations

import os
import uuid

import magic
from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AuthorizationError, NotFoundError, ServiceUnavailableError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_user_optional, require_permission
from app.models.system import FileObject
from app.models.user import User

router = APIRouter(prefix="/files", tags=["files"])
settings = get_settings()

# Real content-sniffed (libmagic, not the client-supplied Content-Type header,
# which is trivially spoofable) allowlist. Kept intentionally small: this is
# for lesson media/resources and avatar-style images, not general file
# storage. Extend deliberately, not by widening a wildcard.
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
    return f"{settings.API_V1_PREFIX}/files/{file_id}"


@router.post("", response_model=FileOut, status_code=201)
async def upload_file(
    file: UploadFile,
    visibility: str = Query("private", pattern=r"^(private|public)$"),
    user: User = Depends(require_permission("files.upload")),
    db: AsyncSession = Depends(get_db),
):
    if settings.STORAGE_BACKEND != "local":
        # S3 backend is a documented, planned setting — not implemented in
        # this build (see docs/DEPLOYMENT.md). Fail loudly rather than
        # silently writing to local disk while claiming S3 is active.
        raise ServiceUnavailableError("File storage backend is not available in this deployment.")

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

    # Sniff the real type from file bytes — never trust file.content_type,
    # which the client sets and can set to anything regardless of the actual
    # bytes sent.
    sniffed_mime = magic.from_buffer(content, mime=True)
    if sniffed_mime not in _ALLOWED_MIME_TO_EXT:
        raise ValidationAppError(f"File type '{sniffed_mime}' is not permitted. Allowed: images, PDF, mp4/webm video.")

    ext = _ALLOWED_MIME_TO_EXT[sniffed_mime]
    storage_key = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(settings.STORAGE_LOCAL_PATH, storage_key)
    os.makedirs(settings.STORAGE_LOCAL_PATH, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(content)

    original_filename = os.path.basename(file.filename or "upload")[:255]
    record = FileObject(
        owner_id=user.id, storage_backend="local", storage_key=storage_key,
        original_filename=original_filename, mime_type=sniffed_mime, size_bytes=total,
        visibility=visibility,
        # No virus scanner is wired up in this build — scan_status stays
        # "pending" rather than falsely claiming "clean" (spec's scan_status
        # field is a real hook for a future ClamAV/S3-scan integration, not
        # decoration). See docs/SECURITY.md.
        scan_status="pending",
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
    if record.storage_backend != "local":
        raise ServiceUnavailableError("File storage backend is not available in this deployment.")
    path = os.path.join(settings.STORAGE_LOCAL_PATH, record.storage_key)
    if not os.path.isfile(path):
        raise NotFoundError("File not found.")
    return FileResponse(path, media_type=record.mime_type, filename=record.original_filename)
