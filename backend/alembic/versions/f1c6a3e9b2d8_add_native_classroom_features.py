"""Add native Classroom features: Stream, Classwork, Grades.

Announcements (+comments) and Assignments (+submissions +private comments)
for the native, no-OAuth "Classroom" experience — see
app/models/classroom.py's module docstring. "People" needs no table of its
own; it's derived from Course.instructor_id + Enrollment.

Revision ID: f1c6a3e9b2d8
Revises: e8b3f1a9c4d7
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f1c6a3e9b2d8"
down_revision = "e8b3f1a9c4d7"
branch_labels = None
depends_on = None


def _id_timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "announcements",
        *_id_timestamps(),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_announcements_course_id", "announcements", ["course_id"])

    op.create_table(
        "announcement_comments",
        *_id_timestamps(),
        sa.Column("announcement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
    )
    op.create_index("ix_announcement_comments_announcement_id", "announcement_comments", ["announcement_id"])

    op.create_table(
        "assignments",
        *_id_timestamps(),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("points_possible", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("attachments", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_assignments_course_id", "assignments", ["course_id"])

    op.create_table(
        "assignment_submissions",
        *_id_timestamps(),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("attachments", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_submitted"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grade", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("graded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('not_submitted', 'submitted', 'graded', 'returned')", name="ck_assignment_submissions_status_valid"
        ),
        sa.CheckConstraint("grade IS NULL OR grade >= 0", name="ck_assignment_submissions_grade_non_negative"),
        sa.UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),
    )
    op.create_index("ix_assignment_submissions_assignment_id", "assignment_submissions", ["assignment_id"])
    op.create_index("ix_assignment_submissions_student_id", "assignment_submissions", ["student_id"])

    op.create_table(
        "assignment_comments",
        *_id_timestamps(),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assignment_submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
    )
    op.create_index("ix_assignment_comments_submission_id", "assignment_comments", ["submission_id"])


def downgrade() -> None:
    op.drop_table("assignment_comments")
    op.drop_table("assignment_submissions")
    op.drop_table("assignments")
    op.drop_table("announcement_comments")
    op.drop_table("announcements")
