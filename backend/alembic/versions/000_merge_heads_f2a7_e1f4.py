"""merge divergent migration heads

Revision ID: 000_merge_heads_f2a7_e1f4
Revises: e1f4a6b8c2d0, f2a7c9e1b4d6
Create Date: 2026-08-16

The V2 PR merges (#29/#31/#32/#35) introduced two divergent migration
branches:
  - f2a7c9e1b4d6 (push subscriptions, branched from d18e6b4a3f57)
  - e1f4a6b8c2d0 (upgrade contest certificates, branched from c9d4e7a1f6b8)

Both were valid migrations off different points in the chain. This merge
migration ties them into a single head so `alembic upgrade head` resolves
to exactly one revision.
"""
from alembic import op

revision = "000_merge_heads_f2a7_e1f4"
down_revision = ("e1f4a6b8c2d0", "f2a7c9e1b4d6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
