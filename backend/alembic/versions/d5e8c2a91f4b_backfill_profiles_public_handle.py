"""Backfill profiles.public_handle for accounts that predate the
required-at-signup username (see app.services.profile_service and
POST /auth/register). Every account created from here on already gets a
real, chosen handle; this only touches rows left over from before that
requirement existed. Uses the same deterministic-from-id scheme as
profile_service.fallback_handle() so it can never collide.

Revision ID: d5e8c2a91f4b
Revises: 3c967f321292
"""
from __future__ import annotations

from alembic import op

revision: str = "d5e8c2a91f4b"
down_revision: str | None = "3c967f321292"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE profiles SET public_handle = 'user_' || substr(replace(user_id::text, '-', ''), 1, 12) "
        "WHERE public_handle IS NULL"
    )


def downgrade() -> None:
    # Not reversible in a meaningful way — the original "null" state carried
    # no information worth restoring, and other rows may have since taken a
    # handle that collides with what we'd be nulling back out.
    pass
