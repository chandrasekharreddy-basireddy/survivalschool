"""Add chat_room_id to elimination_battles — every battle gets its own
live chat room, reusing the existing chat_rooms/chat_members/chat_messages
tables and /ws/chat/{room_id} socket rather than a separate persistence
path (see elimination_service.create_battle).

Revision ID: c4e8a2f6b9d3
Revises: f9b3d6a1c8e2
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4e8a2f6b9d3"
down_revision: str | None = "f9b3d6a1c8e2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "elimination_battles",
        sa.Column("chat_room_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_rooms.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("elimination_battles", "chat_room_id")
