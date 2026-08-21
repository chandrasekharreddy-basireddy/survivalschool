"""Add profiles.school — disambiguates campus timetable section lookups
across schools, since section numbers repeat (e.g. both an "SCDS Section A"
and an "SOAI Section A" can exist). Nullable: existing accounts that only
ever set section keep matching on section alone.

Revision ID: e2c8a5d1f7b4
Revises: a4f7c1e9b3d6
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "e2c8a5d1f7b4"
down_revision: str | None = "a4f7c1e9b3d6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("school", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "school")
