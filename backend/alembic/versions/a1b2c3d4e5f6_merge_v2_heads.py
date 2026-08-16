"""merge divergent v2 migration heads

Revision ID: a1b2c3d4e5f6
Revises: e1f4a6b8c2d0, e7c4f1a2b9d0
Create Date: 2026-08-16

The V2 PR merges (#29/#31/#32/#35) introduced two divergent migration
branches off c9d4e7a1f6b8:
  - e1f4a6b8c2d0 (upgrade contest certificates, from PR #31)
  - e7c4f1a2b9d0 (harden v2 scheduling RLS, from PR #32)

This merge migration ties both into a single head so `alembic upgrade head`
resolves to exactly one revision.
"""
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = ("e1f4a6b8c2d0", "e7c4f1a2b9d0")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
