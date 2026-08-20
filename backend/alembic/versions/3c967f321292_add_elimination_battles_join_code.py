"""Add elimination_battles.join_code — a shareable room code (and QR,
which just encodes a URL containing this code) that lets anyone holding it
join the lobby directly, no invitation or prior connection required. This
table is new in this same pivot and has no production rows yet, but any
pre-existing row is still backfilled with a real unique code rather than
assuming there are none.

Revision ID: 3c967f321292
Revises: 1cf6c8faebce
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "3c967f321292"
down_revision: str | None = "1cf6c8faebce"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("elimination_battles", sa.Column("join_code", sa.String(length=8), nullable=True))
    op.execute(
        "UPDATE elimination_battles SET join_code = upper(substr(md5(random()::text || id::text), 1, 6)) "
        "WHERE join_code IS NULL"
    )
    op.alter_column("elimination_battles", "join_code", nullable=False)
    op.create_unique_constraint("uq_elimination_battle_join_code", "elimination_battles", ["join_code"])


def downgrade() -> None:
    op.drop_constraint("uq_elimination_battle_join_code", "elimination_battles", type_="unique")
    op.drop_column("elimination_battles", "join_code")
