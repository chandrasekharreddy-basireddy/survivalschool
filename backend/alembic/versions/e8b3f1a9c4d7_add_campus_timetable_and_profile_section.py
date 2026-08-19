"""Add campus timetable tables and profiles.section.

Two new tables for the university-wide campus timetable feature — deliberately
separate from timetable_entries (which is scoped to this platform's own
courses), see app/models/campus_timetable.py's module docstring — plus a
profiles.section column so a student's personal campus schedule
(GET /timetable/campus/me) can be filtered without guessing.

Revision ID: e8b3f1a9c4d7
Revises: d4f1a8c3e6b9
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e8b3f1a9c4d7"
down_revision = "d4f1a8c3e6b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("section", sa.String(60), nullable=True))

    op.create_table(
        "campus_timetable_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("singleton", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mode", sa.String(20), nullable=False, server_default="upload"),
        sa.Column("sheet_csv_url", sa.String(2048), nullable=True),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(20), nullable=True),
        sa.Column("last_sync_error", sa.String(500), nullable=True),
        sa.Column("last_sync_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("mode IN ('upload', 'live_sync')", name="ck_campus_timetable_sources_mode_valid"),
        sa.UniqueConstraint("singleton", name="uq_campus_timetable_source_singleton"),
    )

    op.create_table(
        "campus_timetable_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_key", sa.String(64), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("school", sa.String(120), nullable=True),
        sa.Column("academic_year", sa.String(20), nullable=True),
        sa.Column("section", sa.String(60), nullable=False),
        sa.Column("lab_group", sa.String(60), nullable=True),
        sa.Column("course_name", sa.String(200), nullable=False),
        sa.Column("course_code", sa.String(40), nullable=True),
        sa.Column("class_date", sa.Date(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("room", sa.String(100), nullable=True),
        sa.Column("teacher_name", sa.String(150), nullable=True),
        sa.Column("is_elective", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(20), nullable=False, server_default="upload"),
        sa.CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_campus_timetable_entries_day_of_week_valid"),
        sa.CheckConstraint("source IN ('upload', 'live_sync')", name="ck_campus_timetable_entries_source_valid"),
        sa.UniqueConstraint("row_key", name="uq_campus_timetable_entry_row_key"),
    )
    op.create_index("ix_campus_timetable_section_date", "campus_timetable_entries", ["section", "class_date"])


def downgrade() -> None:
    op.drop_index("ix_campus_timetable_section_date", table_name="campus_timetable_entries")
    op.drop_table("campus_timetable_entries")
    op.drop_table("campus_timetable_sources")
    op.drop_column("profiles", "section")
