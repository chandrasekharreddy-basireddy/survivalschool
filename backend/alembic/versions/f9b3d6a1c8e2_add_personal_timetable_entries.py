"""Add personal_timetable_entries — a student's own uploaded schedule,
deliberately a separate table from campus_timetable_entries so a student's
file can never touch the shared, institution-wide feed.

Revision ID: f9b3d6a1c8e2
Revises: e2c8a5d1f7b4
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f9b3d6a1c8e2"
down_revision: str | None = "e2c8a5d1f7b4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "personal_timetable_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_name", sa.String(length=200), nullable=False),
        sa.Column("course_code", sa.String(length=40), nullable=True),
        sa.Column("class_date", sa.Date(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("room", sa.String(length=100), nullable=True),
        sa.Column("teacher_name", sa.String(length=150), nullable=True),
        sa.Column("is_elective", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_personal_timetable_entries_user_id", "personal_timetable_entries", ["user_id"])
    op.create_index("ix_personal_timetable_user_date", "personal_timetable_entries", ["user_id", "class_date"])


def downgrade() -> None:
    op.drop_index("ix_personal_timetable_user_date", table_name="personal_timetable_entries")
    op.drop_index("ix_personal_timetable_entries_user_id", table_name="personal_timetable_entries")
    op.drop_table("personal_timetable_entries")
