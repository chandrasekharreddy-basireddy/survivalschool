"""Add ai_messages.image_file_id for AI assistant image uploads.

Revision ID: c3e9f7a2b5d1
Revises: a7d2c8f4e1b3
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c3e9f7a2b5d1"
down_revision = "a7d2c8f4e1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_messages", sa.Column("image_file_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_ai_messages_image_file_id_files", "ai_messages", "files", ["image_file_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_ai_messages_image_file_id_files", "ai_messages", type_="foreignkey")
    op.drop_column("ai_messages", "image_file_id")
