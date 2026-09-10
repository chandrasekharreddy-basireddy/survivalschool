"""Add classroom system: classrooms, members, exams, attempts, answers.

Revision ID: b5d8e2f4a7c1
Revises: a4e9c2f7b3d6
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b5d8e2f4a7c1"
down_revision: str | None = "a4e9c2f7b3d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classrooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("section", sa.String(50), server_default="", nullable=False),
        sa.Column("join_code", sa.String(8), nullable=False),
        sa.Column("lecturer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_classrooms_lecturer_id", "classrooms", ["lecturer_id"])
    op.create_unique_constraint("uq_classrooms_join_code", "classrooms", ["join_code"])

    op.create_table(
        "classroom_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_classroom_member", "classroom_members", ["classroom_id", "student_id"])
    op.create_index("ix_classroom_members_student_id", "classroom_members", ["student_id"])

    op.create_table(
        "classroom_exams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("classroom_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("question_ids", postgresql.JSON(), server_default="[]", nullable=False),
        sa.Column("duration_seconds", sa.Integer(), server_default="1800", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fullscreen_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("integrity_monitoring_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("max_integrity_violations", sa.Integer(), server_default="5", nullable=False),
        sa.Column("max_warnings_before_terminate", sa.Integer(), server_default="2", nullable=False),
        sa.Column("face_proctoring_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'scheduled', 'open', 'closed')", name="classroom_exam_status_valid"),
    )
    op.create_index("ix_classroom_exams_classroom_id", "classroom_exams", ["classroom_id"])
    op.create_index("ix_classroom_exams_status", "classroom_exams", ["status"])

    op.create_table(
        "classroom_exam_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("classroom_exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_order", postgresql.JSON(), server_default="[]", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("server_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_taken_seconds", sa.Integer(), nullable=True),
        sa.Column("score_percent", sa.Integer(), nullable=True),
        sa.Column("points_earned", sa.Integer(), nullable=True),
        sa.Column("points_possible", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), server_default="in_progress", nullable=False),
        sa.Column("device_fingerprint", sa.String(256), nullable=True),
        sa.Column("violation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("warning_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("flagged_events", postgresql.JSON(), server_default="[]", nullable=False),
        sa.CheckConstraint("status IN ('in_progress', 'submitted', 'terminated')", name="classroom_exam_attempt_status_valid"),
    )
    op.create_unique_constraint("uq_classroom_exam_attempt_student", "classroom_exam_attempts", ["exam_id", "student_id"])
    op.create_index("ix_classroom_exam_attempts_exam_id", "classroom_exam_attempts", ["exam_id"])
    op.create_index("ix_classroom_exam_attempts_student_id", "classroom_exam_attempts", ["student_id"])

    op.create_table(
        "classroom_exam_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("classroom_exam_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("selected_option_ids", postgresql.JSON(), server_default="[]", nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("points_awarded", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_classroom_exam_answers_attempt_id", "classroom_exam_answers", ["attempt_id"])

    # RLS: deny-all for PostgREST (same pattern as every other table)
    for table in ("classrooms", "classroom_members", "classroom_exams", "classroom_exam_attempts", "classroom_exam_answers"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY deny_direct_api_access ON {table} AS RESTRICTIVE "
            f"FOR ALL TO PUBLIC USING (false) WITH CHECK (false)"
        )

    # Add warning_count to contest_attempts for the warning system
    op.add_column("contest_attempts", sa.Column("warning_count", sa.Integer(), server_default="0", nullable=False))
    # Add max_warnings_before_terminate to contests
    op.add_column("contests", sa.Column("max_warnings_before_terminate", sa.Integer(), server_default="2", nullable=False))


def downgrade() -> None:
    op.drop_column("contests", "max_warnings_before_terminate")
    op.drop_column("contest_attempts", "warning_count")
    for table in ("classroom_exam_answers", "classroom_exam_attempts", "classroom_exams", "classroom_members", "classrooms"):
        op.execute(f"DROP POLICY IF EXISTS deny_direct_api_access ON {table}")
        op.drop_table(table)
