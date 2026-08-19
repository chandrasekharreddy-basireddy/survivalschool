from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social_graph import FollowRequest


async def has_accepted_connection(db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
    """True once an accepted follow request exists between the two users in
    either direction. This is the single gate messaging.py's direct-message
    endpoint checks — nothing else in the app grants the ability to DM
    someone."""
    row = (await db.execute(
        select(FollowRequest.id).where(
            FollowRequest.status == "accepted",
            or_(
                and_(FollowRequest.requester_id == user_a, FollowRequest.target_id == user_b),
                and_(FollowRequest.requester_id == user_b, FollowRequest.target_id == user_a),
            ),
        )
    )).scalar_one_or_none()
    return row is not None
