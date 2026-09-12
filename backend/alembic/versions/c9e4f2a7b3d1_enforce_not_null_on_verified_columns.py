"""enforce NOT NULL on 4 columns verified to have zero existing NULLs

The remaining piece of the alembic-check drift from b6f3a1d8c5e2, held
back at the time because production data couldn't be verified (Supabase
access was blocked). Directly queried since: all 4 columns have zero
NULL rows in production right now, so this is safe to apply.

Revision ID: c9e4f2a7b3d1
Revises: b6f3a1d8c5e2
Create Date: 2026-09-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9e4f2a7b3d1'
down_revision: Union[str, None] = 'b6f3a1d8c5e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('classroom_exam_attempts', 'started_at', existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column('elimination_answers', 'submitted_at', existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column('elimination_rounds', 'released_at', existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column('topic_difficulty_evaluations', 'evaluated_at', existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    op.alter_column('topic_difficulty_evaluations', 'evaluated_at', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column('elimination_rounds', 'released_at', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column('elimination_answers', 'submitted_at', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column('classroom_exam_attempts', 'started_at', existing_type=sa.DateTime(timezone=True), nullable=True)
