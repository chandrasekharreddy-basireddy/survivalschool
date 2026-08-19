"""Add follow_requests table.

Instagram-style follow requests — see app/models/social_graph.py's module
docstring. An accepted request is the sole gate for direct messaging
(app/services/social_graph_service.py::has_accepted_connection, checked by
POST /chat/dm/{user_id}).

Revision ID: a7d2c8f4e1b3
Revises: f1c6a3e9b2d8
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7d2c8f4e1b3"
down_revision = "f1c6a3e9b2d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follow_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("requester_id != target_id", name="ck_follow_request_not_self"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined')", name="ck_follow_request_status_valid"),
        sa.UniqueConstraint("requester_id", "target_id", name="uq_follow_request_pair"),
    )
    op.create_index("ix_follow_requests_requester_id", "follow_requests", ["requester_id"])
    op.create_index("ix_follow_requests_target_id", "follow_requests", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_follow_requests_target_id", table_name="follow_requests")
    op.drop_index("ix_follow_requests_requester_id", table_name="follow_requests")
    op.drop_table("follow_requests")
