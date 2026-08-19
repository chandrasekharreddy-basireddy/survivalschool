"""Add instructor_applications table.

Instructor onboarding is deliberately NOT the student registration flow
(POST /auth/register, gated by the Thursday weekly-exam registration
window) and deliberately does NOT grant the INSTRUCTOR role directly.
Applying (POST /auth/instructor-applications) only inserts a `pending` row
here; an admin reviewing it through POST/admin/instructor-applications/
{id}/approve is what actually grants INSTRUCTOR, via the same audited
POST /users/{id}/roles/{role} path already used for every other role
change. This keeps privilege escalation admin-reviewed and out of
self-service signup, consistent with the rest of the RBAC design.

Revision ID: d4f1a8c3e6b9
Revises: c7e2a9f4b016
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4f1a8c3e6b9"
down_revision = "c7e2a9f4b016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instructor_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("institution", sa.String(200), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(1000), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status_valid"),
    )
    op.create_index("ix_instructor_applications_user_id", "instructor_applications", ["user_id"])
    op.create_index("ix_instructor_applications_status", "instructor_applications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_instructor_applications_status", table_name="instructor_applications")
    op.drop_index("ix_instructor_applications_user_id", table_name="instructor_applications")
    op.drop_table("instructor_applications")
