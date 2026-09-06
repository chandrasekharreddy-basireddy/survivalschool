"""audit: missing indexes and enum-like check constraints

Revision ID: 7124438c94d6
Revises: c4e8a2f6b9d3
Create Date: 2026-09-03 00:00:00.000000

Found during a full codebase audit. Every index below is backed by an
actual hot query; every check constraint mirrors an existing pattern
already used on other status-like columns in this schema
(ContestAttempt.status's "status_valid" being the direct precedent):

- ix_chat_members_room_user (chat_members.room_id, chat_members.user_id):
  every membership check (_assert_member, the WS connect check, the
  chat.message/chat.read handlers) queries exactly this pair — the existing
  single-column indexes on room_id/user_id separately can't serve it as
  directly.
- ix_files_owner_id (files.owner_id): the natural lookup key for a future
  "my files" listing; every other FK-into-users column in this schema is
  already indexed.
- ix_elimination_rounds_sweep (elimination_rounds.deadline_at, partial
  WHERE resolved_at IS NULL): the expiry sweep
  (elimination_service._sweep_once) runs this exact WHERE clause every
  2 seconds, unconditionally, for the process's lifetime.
- question_type_valid (questions.question_type IN (...)): an unrecognized
  question_type was silently accepted, skipped create_question's
  option-count validation, and would always grade as incorrect via
  scoring_service.grade_answer's else branch — a dead, unscorable question
  with no error raised anywhere.
- contest_status_valid / contest_type_valid (contests.status / .contest_type
  IN (...)): same class of gap as question_type_valid, on the two Contest
  columns the rest of this codebase branches on by exact string literal.

NOT included: a (user_id, created_at) composite on notifications — that
index already exists, added by c4a91f7d0e2b ("add missing performance
indexes") without ever being reflected back into the SQLAlchemy model.
This revision only fixes that model/migration drift (see
app/models/social.py's Notification.__table_args__), it does not touch
the database again for it.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '7124438c94d6'
down_revision: Union[str, None] = 'c4e8a2f6b9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_chat_members_room_user', 'chat_members', ['room_id', 'user_id'], unique=False)
    op.create_index('ix_files_owner_id', 'files', ['owner_id'], unique=False)
    op.create_index(
        'ix_elimination_rounds_sweep', 'elimination_rounds', ['deadline_at'],
        unique=False, postgresql_where='resolved_at IS NULL',
    )
    op.create_check_constraint(
        'question_type_valid', 'questions',
        "question_type IN ('single', 'multiple', 'true_false', 'short_answer')",
    )
    op.create_check_constraint(
        'contest_status_valid', 'contests',
        "status IN ('scheduled', 'open', 'closed')",
    )
    op.create_check_constraint(
        'contest_type_valid', 'contests',
        "contest_type IN ('ai_weekly', 'weekly_morning', 'weekly_evening', 'monthly', 'custom')",
    )


def downgrade() -> None:
    op.drop_constraint('contest_type_valid', 'contests', type_='check')
    op.drop_constraint('contest_status_valid', 'contests', type_='check')
    op.drop_constraint('question_type_valid', 'questions', type_='check')
    op.drop_index('ix_elimination_rounds_sweep', table_name='elimination_rounds')
    op.drop_index('ix_files_owner_id', table_name='files')
    op.drop_index('ix_chat_members_room_user', table_name='chat_members')
