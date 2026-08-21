"""Add elimination_battles.scheduled_start_at — lets the host schedule an
auto-start instead of clicking Start themselves, enforced by the sweep
loop in elimination_service.py.

Revision ID: a4f7c1e9b3d6
Revises: d5e8c2a91f4b
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "a4f7c1e9b3d6"
down_revision: str | None = "d5e8c2a91f4b"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("elimination_battles", sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("elimination_battles", "scheduled_start_at")
