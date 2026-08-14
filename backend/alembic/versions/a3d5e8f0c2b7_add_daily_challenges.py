"""add daily_challenges and daily_challenge_attempts

Revision ID: a3d5e8f0c2b7
Revises: f2a7c9e1b4d6
Create Date: 2026-08-14 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a3d5e8f0c2b7'
down_revision: Union[str, None] = 'f2a7c9e1b4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'daily_challenges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('challenge_date', sa.Date(), nullable=False),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_daily_challenges_challenge_date', 'daily_challenges', ['challenge_date'])
    op.create_unique_constraint('uq_daily_challenge_date', 'daily_challenges', ['challenge_date'])

    op.create_table(
        'daily_challenge_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('challenge_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('daily_challenges.id', ondelete='CASCADE'), nullable=False),
        sa.Column('selected_option_ids', sa.JSON(), nullable=False),
        sa.Column('text_answer', sa.Text(), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=False),
        sa.Column('points_awarded', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_daily_challenge_attempts_student_id', 'daily_challenge_attempts', ['student_id'])
    op.create_index('ix_daily_challenge_attempts_challenge_id', 'daily_challenge_attempts', ['challenge_id'])
    op.create_unique_constraint('uq_daily_challenge_attempt', 'daily_challenge_attempts', ['student_id', 'challenge_id'])


def downgrade() -> None:
    op.drop_constraint('uq_daily_challenge_attempt', 'daily_challenge_attempts', type_='unique')
    op.drop_index('ix_daily_challenge_attempts_challenge_id', table_name='daily_challenge_attempts')
    op.drop_index('ix_daily_challenge_attempts_student_id', table_name='daily_challenge_attempts')
    op.drop_table('daily_challenge_attempts')

    op.drop_constraint('uq_daily_challenge_date', 'daily_challenges', type_='unique')
    op.drop_index('ix_daily_challenges_challenge_date', table_name='daily_challenges')
    op.drop_table('daily_challenges')
