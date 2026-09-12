"""drop orphaned contest columns, reconcile files/contest_attempts unique indexes

Only the parts of the alembic-check drift that are safe regardless of
existing data: dropping columns/indexes never fails on data content, and
converting an index that ALREADY enforces uniqueness into an equivalent
unique constraint (or vice versa) can't fail either, since the uniqueness
it's replacing was already guaranteed. The NOT NULL changes flagged by the
same drift check are deliberately NOT included here -- those could fail
outright if any existing row has a NULL in that column, and that couldn't
be verified against production data before writing this migration.

Revision ID: b6f3a1d8c5e2
Revises: c2b8f4a1d9e7
Create Date: 2026-09-12 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b6f3a1d8c5e2'
down_revision: Union[str, None] = 'c2b8f4a1d9e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # contests.max_warnings_before_terminate / contest_attempts.warning_count:
    # confirmed zero references anywhere in app/ -- orphaned since contests
    # moved to the shared violation_count/allowed_ip integrity model.
    op.drop_column("contests", "max_warnings_before_terminate")
    op.drop_column("contest_attempts", "warning_count")

    # files.uq_file_backend_key: DB has this as a plain unique INDEX; the
    # model declares it as a named UNIQUE CONSTRAINT. Same effect, different
    # construct -- convert to match the model. Safe: the constraint can only
    # fail to create if a duplicate already exists, and the index being
    # replaced already proves none does.
    op.drop_index("uq_file_backend_key", table_name="files")
    op.create_unique_constraint("uq_file_backend_key", "files", ["storage_backend", "storage_key"])

    # contest_attempts.submission_client_token: DB has both a named UNIQUE
    # CONSTRAINT and a separate redundant plain INDEX on the same single
    # column -- the model just wants one unique index (unique=True,
    # index=True inline). Drop both old objects, create the one the model
    # expects. Safe for the same reason as above: the existing constraint
    # already proves the column has no duplicate values.
    op.drop_index("ix_contest_attempts_submission_client_token", table_name="contest_attempts")
    op.drop_constraint("uq_contest_attempts_submission_client_token", "contest_attempts", type_="unique")
    op.create_index(
        "ix_contest_attempts_submission_client_token", "contest_attempts",
        ["submission_client_token"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_contest_attempts_submission_client_token", table_name="contest_attempts")
    op.create_unique_constraint(
        "uq_contest_attempts_submission_client_token", "contest_attempts", ["submission_client_token"]
    )
    op.create_index(
        "ix_contest_attempts_submission_client_token", "contest_attempts", ["submission_client_token"]
    )

    op.drop_constraint("uq_file_backend_key", "files", type_="unique")
    op.create_index("uq_file_backend_key", "files", ["storage_backend", "storage_key"], unique=True)

    op.add_column("contest_attempts", sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("contests", sa.Column("max_warnings_before_terminate", sa.Integer(), nullable=False, server_default="2"))
