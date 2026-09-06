"""add contest face_proctoring_required

Revision ID: 3bf82d268141
Revises: d3f6a9c2e7b1
Create Date: 2026-09-06 17:28:09.134049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3bf82d268141'
down_revision: Union[str, None] = 'd3f6a9c2e7b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contests",
        sa.Column("face_proctoring_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("contests", "face_proctoring_required", server_default=None)


def downgrade() -> None:
    op.drop_column("contests", "face_proctoring_required")
