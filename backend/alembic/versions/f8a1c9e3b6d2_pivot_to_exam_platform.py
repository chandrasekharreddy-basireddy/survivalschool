"""Pivot to competitive exam platform: destroy courses/LMS entirely, add
Subject/Topic taxonomy, AI Weekly Exam registration/integrity fields on
contests, and the elimination-battle engine. Campus-wide timetable
(campus_timetable_entries / campus_timetable_sources) is untouched — it was
never course-coupled.

Drop order is FK-dependency-safe (children before parents). Every new
foreign key is given an explicit name matching this project's naming
convention (fk_<table>_<column>_<referred_table>) rather than left for
Postgres to default-name — see migration c7e2a9f4b016's fix earlier in this
project's history for exactly why an unnamed constraint created outside
Base.metadata's naming_convention causes a later migration to fail trying
to guess its name.

Revision ID: f8a1c9e3b6d2
Revises: e5b8d2f6a9c4
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f8a1c9e3b6d2"
down_revision = "e5b8d2f6a9c4"
branch_labels = None
depends_on = None


def _fk(table: str, column: str, referred: str) -> str:
    return f"fk_{table}_{column}_{referred}"


def upgrade() -> None:
    # ---- 0. Drop every FK from a SURVIVING table into `courses` first -----
    # These four tables aren't being dropped themselves — only their
    # course_id/course_context_id column goes away later in this migration
    # (steps 4/6) — but their FK constraint has to be gone before `courses`
    # itself can be dropped in step 1, or Postgres refuses with
    # DependentObjectsStillExistError.
    op.drop_constraint(_fk("ai_conversations", "course_context_id", "courses"), "ai_conversations", type_="foreignkey")
    op.drop_constraint(_fk("chat_rooms", "course_id", "courses"), "chat_rooms", type_="foreignkey")
    op.drop_constraint(_fk("practice_sessions", "course_id", "courses"), "practice_sessions", type_="foreignkey")
    op.drop_constraint(_fk("questions", "course_id", "courses"), "questions", type_="foreignkey")

    # ---- 1. Drop LMS/course-coupled tables, children first ----------------
    op.drop_table("lesson_resources")
    op.drop_table("discussion_replies")
    op.drop_table("discussion_votes")
    op.drop_table("discussion_threads")
    op.drop_table("announcement_comments")
    op.drop_table("announcements")
    op.drop_table("assignment_comments")
    op.drop_table("assignment_submissions")
    op.drop_table("assignments")
    op.drop_table("attendance_records")
    op.drop_table("attendance_sessions")
    op.drop_table("quiz_answers")
    op.drop_table("quiz_attempts")
    op.drop_table("quizzes")
    op.drop_table("exam_answers")
    op.drop_table("exam_attempts")
    op.drop_table("exams")
    op.drop_table("scheduled_exam_configs")
    op.drop_table("certificates")
    op.drop_table("timetable_entries")
    op.drop_table("course_progress")
    op.drop_table("lesson_progress")
    op.drop_table("enrollments")
    op.drop_table("lessons")
    op.drop_table("course_sections")
    op.drop_table("courses")

    # ---- 2. Rename registration_windows -> ai_exam_registration_windows ---
    op.execute("ALTER TABLE registration_windows RENAME CONSTRAINT uq_registration_window_singleton TO uq_ai_exam_registration_window_singleton")
    op.rename_table("registration_windows", "ai_exam_registration_windows")

    # ---- 3. New taxonomy tables --------------------------------------------
    op.create_table(
        "universities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("singleton", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("singleton", name="uq_university_singleton"),
    )
    op.create_table(
        "subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], name=_fk("subjects", "university_id", "universities"), ondelete="CASCADE"),
        sa.UniqueConstraint("university_id", "slug", name="uq_subject_university_slug"),
    )
    op.create_index("ix_subjects_university_id", "subjects", ["university_id"])
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], name=_fk("topics", "subject_id", "subjects"), ondelete="CASCADE"),
        sa.UniqueConstraint("subject_id", "slug", name="uq_topic_subject_slug"),
    )
    op.create_index("ix_topics_subject_id", "topics", ["subject_id"])
    op.create_table(
        "topic_difficulty_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("difficulty_percent", sa.Integer(), nullable=False),
        sa.Column("formula_version", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name=_fk("topic_difficulty_evaluations", "topic_id", "topics"), ondelete="CASCADE"),
    )
    op.create_index("ix_topic_difficulty_evaluations_topic_id", "topic_difficulty_evaluations", ["topic_id"])

    # ---- 4. Repoint questions from course_id to subject_id/topic_id -------
    # (FK constraint already dropped in step 0)
    op.drop_column("questions", "course_id")
    op.add_column("questions", sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("questions", sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("questions", sa.Column("is_ai_generated", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("questions", sa.Column("is_validated", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_foreign_key(_fk("questions", "subject_id", "subjects"), "questions", "subjects", ["subject_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(_fk("questions", "topic_id", "topics"), "questions", "topics", ["topic_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_questions_subject_id", "questions", ["subject_id"])
    op.create_index("ix_questions_topic_id", "questions", ["topic_id"])

    # ---- 5. Contests: AI Weekly Exam + integrity-monitoring fields --------
    op.add_column("contests", sa.Column("fullscreen_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("contests", sa.Column("integrity_monitoring_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("contests", sa.Column("max_integrity_violations", sa.Integer(), nullable=False, server_default="3"))

    op.add_column("contest_attempts", sa.Column("submission_client_token", sa.String(128), nullable=True))
    op.add_column("contest_attempts", sa.Column("flagged_events", postgresql.JSON(), nullable=False, server_default="[]"))
    op.add_column("contest_attempts", sa.Column("allowed_ip", sa.String(64), nullable=True))
    op.add_column("contest_attempts", sa.Column("violation_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_contest_attempts_submission_client_token", "contest_attempts", ["submission_client_token"])
    op.create_index("ix_contest_attempts_submission_client_token", "contest_attempts", ["submission_client_token"])
    op.drop_constraint("status_valid", "contest_attempts", type_="check")
    op.create_check_constraint("status_valid", "contest_attempts", "status IN ('registered', 'in_progress', 'submitted', 'abandoned')")

    # ---- 6. Drop course_id/course_context_id from tables that keep the rest
    #         of their shape (practice_sessions, chat_rooms, ai_conversations)
    #         (FK constraints already dropped in step 0) ---------------------
    op.drop_index("ix_practice_sessions_course_id", table_name="practice_sessions")
    op.drop_column("practice_sessions", "course_id")
    op.drop_column("chat_rooms", "course_id")
    op.drop_column("ai_conversations", "course_context_id")

    # ---- 7. Public handle on profiles --------------------------------------
    op.add_column("profiles", sa.Column("public_handle", sa.String(30), nullable=True))
    op.create_unique_constraint("uq_profiles_public_handle", "profiles", ["public_handle"])

    # ---- 8. Elimination battle engine --------------------------------------
    op.create_table(
        "elimination_battles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_round_number", sa.Integer(), nullable=False),
        sa.Column("winner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["host_id"], ["users.id"], name=_fk("elimination_battles", "host_id", "users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name=_fk("elimination_battles", "topic_id", "topics"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["winner_id"], ["users.id"], name=_fk("elimination_battles", "winner_id", "users"), ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('lobby', 'active', 'completed', 'cancelled')", name="ck_elimination_battle_status"),
    )
    op.create_index("ix_elimination_battles_host_id", "elimination_battles", ["host_id"])
    op.create_index("ix_elimination_battles_topic_id", "elimination_battles", ["topic_id"])

    op.create_table(
        "elimination_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("battle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inviter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["battle_id"], ["elimination_battles.id"], name=_fk("elimination_invitations", "battle_id", "elimination_battles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], name=_fk("elimination_invitations", "inviter_id", "users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_id"], ["users.id"], name=_fk("elimination_invitations", "invitee_id", "users"), ondelete="CASCADE"),
        sa.UniqueConstraint("battle_id", "invitee_id", name="uq_elimination_invite_battle_invitee"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'expired')", name="ck_elimination_invite_status"),
        sa.CheckConstraint("inviter_id != invitee_id", name="ck_elimination_invite_not_self"),
    )
    op.create_index("ix_elimination_invitations_battle_id", "elimination_invitations", ["battle_id"])
    op.create_index("ix_elimination_invitations_invitee_id", "elimination_invitations", ["invitee_id"])

    op.create_table(
        "elimination_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("battle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("eliminated_at_round", sa.Integer(), nullable=True),
        sa.Column("eliminated_reason", sa.String(30), nullable=True),
        sa.ForeignKeyConstraint(["battle_id"], ["elimination_battles.id"], name=_fk("elimination_participants", "battle_id", "elimination_battles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=_fk("elimination_participants", "user_id", "users"), ondelete="CASCADE"),
        sa.UniqueConstraint("battle_id", "user_id", name="uq_elimination_participant_battle_user"),
        sa.CheckConstraint("status IN ('ready', 'active', 'eliminated', 'winner')", name="ck_elimination_participant_status"),
    )
    op.create_index("ix_elimination_participants_battle_id", "elimination_participants", ["battle_id"])
    op.create_index("ix_elimination_participants_user_id", "elimination_participants", ["user_id"])

    op.create_table(
        "elimination_rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("battle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["battle_id"], ["elimination_battles.id"], name=_fk("elimination_rounds", "battle_id", "elimination_battles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], name=_fk("elimination_rounds", "question_id", "questions"), ondelete="RESTRICT"),
        sa.UniqueConstraint("battle_id", "round_number", name="uq_elimination_round_battle_number"),
    )
    op.create_index("ix_elimination_rounds_battle_id", "elimination_rounds", ["battle_id"])
    # Not indexing deadline_at explicitly: the sweep loop's overdue-round scan
    # (WHERE resolved_at IS NULL AND deadline_at < now) is over an always-tiny
    # number of concurrently-active rounds, not worth a dedicated index.

    op.create_table(
        "elimination_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selected_option_ids", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["round_id"], ["elimination_rounds.id"], name=_fk("elimination_answers", "round_id", "elimination_rounds"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["elimination_participants.id"], name=_fk("elimination_answers", "participant_id", "elimination_participants"), ondelete="CASCADE"),
        sa.UniqueConstraint("round_id", "participant_id", name="uq_elimination_answer_round_participant"),
    )
    op.create_index("ix_elimination_answers_round_id", "elimination_answers", ["round_id"])
    op.create_index("ix_elimination_answers_participant_id", "elimination_answers", ["participant_id"])


def downgrade() -> None:
    op.drop_table("elimination_answers")
    op.drop_table("elimination_rounds")
    op.drop_table("elimination_participants")
    op.drop_table("elimination_invitations")
    op.drop_table("elimination_battles")

    op.drop_constraint("uq_profiles_public_handle", "profiles", type_="unique")
    op.drop_column("profiles", "public_handle")

    op.add_column("ai_conversations", sa.Column("course_context_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("chat_rooms", sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("practice_sessions", sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_practice_sessions_course_id", "practice_sessions", ["course_id"])

    op.drop_constraint("status_valid", "contest_attempts", type_="check")
    op.create_check_constraint("status_valid", "contest_attempts", "status IN ('in_progress', 'submitted', 'abandoned')")
    op.drop_index("ix_contest_attempts_submission_client_token", table_name="contest_attempts")
    op.drop_constraint("uq_contest_attempts_submission_client_token", "contest_attempts", type_="unique")
    op.drop_column("contest_attempts", "violation_count")
    op.drop_column("contest_attempts", "allowed_ip")
    op.drop_column("contest_attempts", "flagged_events")
    op.drop_column("contest_attempts", "submission_client_token")

    op.drop_column("contests", "max_integrity_violations")
    op.drop_column("contests", "integrity_monitoring_enabled")
    op.drop_column("contests", "fullscreen_required")

    op.drop_index("ix_questions_topic_id", table_name="questions")
    op.drop_index("ix_questions_subject_id", table_name="questions")
    op.drop_constraint(_fk("questions", "topic_id", "topics"), "questions", type_="foreignkey")
    op.drop_constraint(_fk("questions", "subject_id", "subjects"), "questions", type_="foreignkey")
    op.drop_column("questions", "is_validated")
    op.drop_column("questions", "is_ai_generated")
    op.drop_column("questions", "topic_id")
    op.drop_column("questions", "subject_id")
    op.add_column("questions", sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.drop_table("topic_difficulty_evaluations")
    op.drop_table("topics")
    op.drop_table("subjects")
    op.drop_table("universities")

    op.execute("ALTER TABLE ai_exam_registration_windows RENAME CONSTRAINT uq_ai_exam_registration_window_singleton TO uq_registration_window_singleton")
    op.rename_table("ai_exam_registration_windows", "registration_windows")

    # Recreating the full LMS tree on downgrade is out of scope for this
    # migration — a downgrade past this revision is not a supported path for
    # this product pivot (courses are gone by design, not by accident). If a
    # rollback is ever genuinely needed, restore from the pre-migration
    # database snapshot instead of running this downgrade.
    raise NotImplementedError(
        "Downgrading past the course-removal pivot is not supported — "
        "restore from a pre-migration backup instead."
    )
