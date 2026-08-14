"""add totp 2fa fields to users

Revision ID: d18e6b4a3f57
Revises: c4a91f7d0e2b
Create Date: 2026-08-14 12:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'd18e6b4a3f57'
down_revision: Union[str, None] = 'c4a91f7d0e2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('totp_secret', sa.String(length=64), nullable=True))
    # server_default required here, same reasoning documented in
    # docs/DATABASE.md for the certificate/exam-integrity migrations: these
    # columns are NOT NULL and the users table is non-empty, so a plain
    # ADD COLUMN without a default would fail against existing rows.
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('users', sa.Column('totp_backup_codes', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))


def downgrade() -> None:
    op.drop_column('users', 'totp_backup_codes')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
