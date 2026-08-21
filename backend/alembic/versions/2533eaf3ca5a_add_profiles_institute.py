"""Add profiles.institute — optional, free-text, shown/editable at AI
Weekly Exam registration so it's typed once and auto-filled afterward.

Revision ID: 2533eaf3ca5a
Revises: f8a1c9e3b6d2
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "2533eaf3ca5a"
down_revision: str | None = "f8a1c9e3b6d2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("institute", sa.String(length=150), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "institute")
