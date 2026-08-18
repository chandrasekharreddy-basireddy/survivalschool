"""Add assessment integrity constraints, idempotency uniqueness and missing indexes.

Addresses the audit findings DB-C1 (submission_client_token had no unique index,
so concurrent submits both passed the idempotency check), DB-H1/DB-H2 (no
database-level guard on score ranges or attempt status), DB-H3/DB-H4 (FK columns
used in hot WHERE/JOIN clauses were unindexed) and DB-H5 (replaced_by_id pointed
at refresh_tokens with no FK).

Every index here is built with CREATE INDEX CONCURRENTLY inside an autocommit
block (DB-C2). A plain CREATE INDEX holds ACCESS EXCLUSIVE for the whole build,
which on a populated exam_attempts table blocks every read and write to it —
i.e. it takes the exam system down for the duration. CONCURRENTLY cannot run
inside a transaction, hence the autocommit_block.

CHECK/FK constraints are added NOT VALID first (a brief metadata-only lock that
immediately enforces the rule on all new writes) and validated afterwards under
a weaker SHARE UPDATE EXCLUSIVE lock, so neither step blocks traffic.

Revision ID: b3c8d5f27a91
Revises: a1b2c3d4e5f6
"""
from __future__ import annotations

from alembic import op

revision = "b3c8d5f27a91"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


# (table, index name, column, unique)
_INDEXES = [
    ("exam_attempts", "ix_exam_attempts_submission_client_token", "submission_client_token", True),
    ("exam_answers", "ix_exam_answers_question_id", "question_id", False),
    ("quiz_answers", "ix_quiz_answers_question_id", "question_id", False),
    ("courses", "ix_courses_instructor_id", "instructor_id", False),
]

_SCORE_TABLES = ["exam_attempts", "quiz_attempts"]

_SCORE_CHECKS = [
    ("score_percent_range", "score_percent IS NULL OR (score_percent >= 0 AND score_percent <= 100)"),
    ("points_earned_non_negative", "points_earned IS NULL OR points_earned >= 0"),
    ("points_possible_non_negative", "points_possible IS NULL OR points_possible >= 0"),
    (
        "points_earned_within_possible",
        "points_earned IS NULL OR points_possible IS NULL OR points_earned <= points_possible",
    ),
    ("status_valid", "status IN ('in_progress', 'submitted', 'abandoned')"),
]


def upgrade() -> None:
    # A unique index cannot be built over pre-existing duplicates. Keep the
    # earliest attempt for each token and clear the token on the later ones:
    # the column is only an idempotency marker, so clearing it loses no grading
    # data, and those attempts have long since been submitted.
    op.execute(
        """
        UPDATE exam_attempts a
           SET submission_client_token = NULL
         WHERE a.submission_client_token IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM exam_attempts b
                WHERE b.submission_client_token = a.submission_client_token
                  AND (b.started_at, b.id) < (a.started_at, a.id)
           )
        """
    )

    # Orphaned rotation pointers must go before the FK can be trusted: the
    # refresh-token cleanup job deletes expired rows without clearing the
    # replaced_by_id values that referenced them.
    op.execute(
        """
        UPDATE refresh_tokens r
           SET replaced_by_id = NULL
         WHERE r.replaced_by_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM refresh_tokens t WHERE t.id = r.replaced_by_id)
        """
    )

    with op.get_context().autocommit_block():
        for _table, name, column, unique in _INDEXES:
            op.execute(
                f"CREATE {'UNIQUE ' if unique else ''}INDEX CONCURRENTLY IF NOT EXISTS "
                f"{name} ON {_table} ({column})"
            )

    for table in _SCORE_TABLES:
        for name, expr in _SCORE_CHECKS:
            op.execute(f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_{name} CHECK ({expr}) NOT VALID")
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT ck_{table}_{name}")

    op.execute(
        "ALTER TABLE refresh_tokens ADD CONSTRAINT fk_refresh_tokens_replaced_by_id_refresh_tokens "
        "FOREIGN KEY (replaced_by_id) REFERENCES refresh_tokens (id) ON DELETE SET NULL NOT VALID"
    )
    op.execute("ALTER TABLE refresh_tokens VALIDATE CONSTRAINT fk_refresh_tokens_replaced_by_id_refresh_tokens")


def downgrade() -> None:
    op.execute("ALTER TABLE refresh_tokens DROP CONSTRAINT IF EXISTS fk_refresh_tokens_replaced_by_id_refresh_tokens")

    for table in _SCORE_TABLES:
        for name, _expr in _SCORE_CHECKS:
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{name}")

    with op.get_context().autocommit_block():
        for _table, name, _column, _unique in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
