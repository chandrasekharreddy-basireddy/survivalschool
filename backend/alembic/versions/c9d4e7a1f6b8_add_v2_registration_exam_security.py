"""add v2 registration window, scheduled exams, and exam security fields

Revision ID: c9d4e7a1f6b8
Revises: b7f9c3d1e2a4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c9d4e7a1f6b8"
down_revision = "b7f9c3d1e2a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registration_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("next_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("override_until", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "scheduled_exam_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("time_slot", sa.String(length=5), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("auto_certificate_top_n", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("difficulty", sa.String(length=30), nullable=False, server_default="mixed"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_occurrence_key", sa.String(length=32), nullable=True),
        sa.Column("title_prefix", sa.String(length=120), nullable=False, server_default="Weekend AI Exam"),
        sa.UniqueConstraint("day_of_week", "time_slot", "course_id", name="uq_scheduled_exam_slot_course"),
    )
    op.create_index("ix_scheduled_exam_course_id", "scheduled_exam_configs", ["course_id"])

    op.add_column("exams", sa.Column("max_integrity_violations", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("exams", sa.Column("is_ai_scheduled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("exams", sa.Column("auto_certificate_top_n", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("exam_attempts", sa.Column("allowed_ip", sa.String(length=64), nullable=True))
    op.add_column("exam_attempts", sa.Column("violation_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("exam_attempts", "violation_count")
    op.drop_column("exam_attempts", "allowed_ip")
    op.drop_column("exams", "auto_certificate_top_n")
    op.drop_column("exams", "is_ai_scheduled")
    op.drop_column("exams", "max_integrity_violations")
    op.drop_index("ix_scheduled_exam_course_id", table_name="scheduled_exam_configs")
    op.drop_table("scheduled_exam_configs")
    op.drop_table("registration_windows")
