"""add social_notifications preference field

Revision ID: c5e030e83014
Revises: 7124438c94d6
Create Date: 2026-09-03 00:10:00.000000

Follow-request notifications (category="social") had NO preference field
at all — every one was unconditionally delivered with no way to opt out,
found during a full codebase audit alongside the missing rate limit on
POST /follows/requests (fixed separately, in the API layer). Defaults to
True so existing users see no behavior change until they explicitly turn
it off, matching every other preference column's default in this table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'c5e030e83014'
down_revision: Union[str, None] = '7124438c94d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default required: NOT NULL column, non-empty table (same
    # reasoning as d18e6b4a3f57's totp_enabled/totp_backup_codes).
    op.add_column(
        'notification_preferences',
        sa.Column('social_notifications', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )


def downgrade() -> None:
    op.drop_column('notification_preferences', 'social_notifications')
