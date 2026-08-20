"""Add contest_certificates.contest_type — snapshotted at issuance like
contest_title/rank/score_percent already are, so the AI Weekly Exam wins
leaderboard can filter to contest_type="ai_weekly" without an outer join
through the SET-NULL-able contest_id (a win must never silently disappear
from the leaderboard just because its source contest was later deleted).

Backfilled from the still-existing contest for any pre-existing row;
anything orphaned (contest already deleted) falls back to "weekly_morning"
— the original default contest type — since that information is genuinely
unrecoverable for those rows and this is safer than leaving a NULL.

Revision ID: 1cf6c8faebce
Revises: 2533eaf3ca5a
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "1cf6c8faebce"
down_revision: str | None = "2533eaf3ca5a"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("contest_certificates", sa.Column("contest_type", sa.String(length=30), nullable=True))
    op.execute(
        "UPDATE contest_certificates cc SET contest_type = c.contest_type "
        "FROM contests c WHERE cc.contest_id = c.id"
    )
    op.execute("UPDATE contest_certificates SET contest_type = 'weekly_morning' WHERE contest_type IS NULL")
    op.alter_column("contest_certificates", "contest_type", nullable=False)


def downgrade() -> None:
    op.drop_column("contest_certificates", "contest_type")
