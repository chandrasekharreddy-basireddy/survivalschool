"""add contest_attempts autosave_ciphertext

Revision ID: da52deb320bb
Revises: 3bf82d268141
Create Date: 2026-09-06 18:11:11.366932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'da52deb320bb'
down_revision: Union[str, None] = '3bf82d268141'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contest_attempts", sa.Column("autosave_ciphertext", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contest_attempts", "autosave_ciphertext")
