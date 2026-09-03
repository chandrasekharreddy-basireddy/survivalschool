"""Add webauthn_credentials table for passkey / WebAuthn passwordless login
-- an additional sign-in factor an already-logged-in account opts into from
Settings (POST /auth/passkeys/register/*), plus a password-free way to sign
in later (POST /auth/passkeys/login/*). See app/models/user.py's
WebAuthnCredential for field-by-field rationale.

Revision ID: d3f6a9c2e7b1
Revises: c4e8a2f6b9d3
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d3f6a9c2e7b1"
down_revision: str | None = "c4e8a2f6b9d3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.String(length=1024), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("device_label", sa.String(length=255), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])
    op.create_index("ix_webauthn_credentials_credential_id", "webauthn_credentials", ["credential_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_webauthn_credentials_credential_id", table_name="webauthn_credentials")
    op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials")
    op.drop_table("webauthn_credentials")
