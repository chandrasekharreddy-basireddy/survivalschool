"""Rename campus_timetable_entries.academic_year to year_of_study.

Fixing a naming mistake caught by checking against the actual
y-bow/SaiU-Timetable reference: its "year" field is the student's year *of
study* (1-4), not a calendar/academic year — the old column name implied
the wrong thing even though the stored values were always fine as plain
strings.

Revision ID: e5b8d2f6a9c4
Revises: c3e9f7a2b5d1
"""
from __future__ import annotations

from alembic import op

revision = "e5b8d2f6a9c4"
down_revision = "c3e9f7a2b5d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("campus_timetable_entries", "academic_year", new_column_name="year_of_study")


def downgrade() -> None:
    op.alter_column("campus_timetable_entries", "year_of_study", new_column_name="academic_year")
