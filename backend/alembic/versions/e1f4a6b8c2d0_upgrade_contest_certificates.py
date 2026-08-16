"""upgrade contest certificates with QR, PDF and revocation lifecycle

Revision ID: e1f4a6b8c2d0
Revises: c9d4e7a1f6b8
"""
from alembic import op
import sqlalchemy as sa

revision = "e1f4a6b8c2d0"
down_revision = "c9d4e7a1f6b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contest_certificates", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contest_certificates", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("contest_certificates", "expires_at")
    op.drop_column("contest_certificates", "revoked_at")
