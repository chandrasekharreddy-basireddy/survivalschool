"""add classroom_exam_attempts.allowed_ip for IP binding

Revision ID: c2b8f4a1d9e7
Revises: f7a3e9c2b1d5
Create Date: 2026-09-11 09:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2b8f4a1d9e7'
down_revision: Union[str, None] = 'f7a3e9c2b1d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "classroom_exam_attempts",
        sa.Column("allowed_ip", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("classroom_exam_attempts", "allowed_ip")
