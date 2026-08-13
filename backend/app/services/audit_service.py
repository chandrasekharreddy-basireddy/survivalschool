from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import AuditLog

# Fields that must never be written into audit metadata (spec section 26).
_FORBIDDEN_KEYS = {"password", "password_hash", "token", "refresh_token", "access_token", "secret"}


def _sanitize(metadata: dict) -> dict:
    return {k: v for k, v in metadata.items() if k.lower() not in _FORBIDDEN_KEYS}


async def record_audit_event(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    result: str = "success",
    ip_address: str | None = None,
    request_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        ip_address=ip_address,
        request_id=request_id,
        metadata_json=_sanitize(metadata or {}),
    )
    db.add(entry)
    await db.flush()
