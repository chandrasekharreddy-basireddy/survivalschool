"""add profiles.phone

Revision ID: f7a3e9c2b1d5
Revises: d4c8f1a9e6b2
Create Date: 2026-09-11 09:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a3e9c2b1d5'
down_revision: Union[str, None] = 'd4c8f1a9e6b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("phone", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profiles", "phone")
