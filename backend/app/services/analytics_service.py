from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import AnalyticsEvent

logger = structlog.get_logger(__name__)


async def track_event(
    db: AsyncSession,
    *,
    event_type: str,
    user_id: uuid.UUID | None = None,
    session_id: str | None = None,
    source: str = "web",
    metadata: dict | None = None,
) -> None:
    """Fire-and-forget-ish event capture into the append-only analytics stream
    that feeds the Power BI dataset (spec sections 23-24). Deliberately never
    raises — analytics must never break a user-facing request."""
    try:
        db.add(
            AnalyticsEvent(
                event_type=event_type,
                user_id=user_id,
                session_id=session_id,
                source=source,
                metadata_json=metadata or {},
            )
        )
        await db.flush()
    except Exception:
        # Deliberately never raises — analytics must never break a user-facing
        # request — but the failure is still logged so it isn't silently lost.
        logger.warning("analytics_track_event_failed", event_type=event_type)
