"""add elimination_participants.ip_address for IP binding

Revision ID: d4c8f1a9e6b2
Revises: b5d8e2f4a7c1
Create Date: 2026-09-11 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4c8f1a9e6b2'
down_revision: Union[str, None] = 'b5d8e2f4a7c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "elimination_participants",
        sa.Column("ip_address", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("elimination_participants", "ip_address")
