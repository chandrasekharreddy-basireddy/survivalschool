"""Stop certificates cascading away, make the registration window a real
singleton, and close remaining constraint/index gaps.

Addresses the second-pass database audit:

- Certificate.course_id / ContestCertificate.contest_id were ON DELETE CASCADE,
  so deleting a course or contest destroyed every credential already awarded
  for it. Both become ON DELETE SET NULL; certificates already snapshot
  everything they display (course_title is added here and backfilled) so they
  stay renderable and publicly verifiable without the parent row.
- registration_windows had no uniqueness at all despite being used as a
  singleton by a SELECT-then-INSERT that an unauthenticated endpoint can
  reach — two concurrent first-hits could each insert one. A `singleton`
  column with a unique constraint makes a second row impossible.
- contest_attempts never got the score/status CHECK constraints that
  exam_attempts and quiz_attempts received in b3c8d5f27a91.
- Missing indexes: contest_certificates.student_id (the "my certificates"
  filter), audit_logs.resource_type / audit_logs.result (admin log search).
- files(storage_backend, storage_key) had no uniqueness, so two rows could
  point at the same physical object.

Indexes are built CONCURRENTLY in an autocommit block, and CHECK/FK
constraints are added NOT VALID then validated, so nothing takes a long
blocking lock on a populated database.

Revision ID: c7e2a9f4b016
Revises: b3c8d5f27a91
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7e2a9f4b016"
down_revision = "b3c8d5f27a91"
branch_labels = None
depends_on = None


_CONTEST_ATTEMPT_CHECKS = [
    ("score_percent_range", "score_percent IS NULL OR (score_percent >= 0 AND score_percent <= 100)"),
    ("points_earned_non_negative", "points_earned IS NULL OR points_earned >= 0"),
    ("points_possible_non_negative", "points_possible IS NULL OR points_possible >= 0"),
    (
        "points_earned_within_possible",
        "points_earned IS NULL OR points_possible IS NULL OR points_earned <= points_possible",
    ),
    ("status_valid", "status IN ('in_progress', 'submitted', 'abandoned')"),
]

# (index name, table, columns, unique)
_INDEXES = [
    ("ix_contest_certificates_student_id", "contest_certificates", "student_id", False),
    ("ix_audit_logs_resource_type", "audit_logs", "resource_type", False),
    ("ix_audit_logs_result", "audit_logs", "result", False),
    ("uq_file_backend_key", "files", "storage_backend, storage_key", True),
]


def _fk_name(table: str, column: str, referred: str) -> str:
    """Match the naming_convention configured on Base.metadata."""
    return f"fk_{table}_{column}_{referred}"


def upgrade() -> None:
    # --- certificates: survive deletion of their course -------------------
    op.add_column("certificates", sa.Column("course_title", sa.String(length=200), nullable=True))
    # Backfill from the live course while the FK still points somewhere.
    op.execute(
        """
        UPDATE certificates c
           SET course_title = co.title
          FROM courses co
         WHERE co.id = c.course_id
           AND c.course_title IS NULL
        """
    )
    op.alter_column("certificates", "course_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)
    op.drop_constraint(_fk_name("certificates", "course_id", "courses"), "certificates", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("certificates", "course_id", "courses"),
        "certificates", "courses", ["course_id"], ["id"], ondelete="SET NULL",
    )

    # --- contest certificates: survive deletion of their contest ----------
    op.alter_column("contest_certificates", "contest_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)
    op.drop_constraint(_fk_name("contest_certificates", "contest_id", "contests"), "contest_certificates", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("contest_certificates", "contest_id", "contests"),
        "contest_certificates", "contests", ["contest_id"], ["id"], ondelete="SET NULL",
    )

    # --- registration window: enforce single-row-ness ---------------------
    op.add_column(
        "registration_windows",
        sa.Column("singleton", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Collapse any duplicates that already exist before the constraint lands,
    # keeping the oldest row (the one get_or_create_window would have picked).
    op.execute(
        """
        DELETE FROM registration_windows r
         WHERE EXISTS (
             SELECT 1 FROM registration_windows keep
              WHERE (keep.created_at, keep.id) < (r.created_at, r.id)
         )
        """
    )
    op.create_unique_constraint("uq_registration_window_singleton", "registration_windows", ["singleton"])

    # --- contest_attempts: parity with exam/quiz attempt guards -----------
    for name, expr in _CONTEST_ATTEMPT_CHECKS:
        op.execute(f"ALTER TABLE contest_attempts ADD CONSTRAINT ck_contest_attempts_{name} CHECK ({expr}) NOT VALID")
        op.execute(f"ALTER TABLE contest_attempts VALIDATE CONSTRAINT ck_contest_attempts_{name}")

    # --- indexes ----------------------------------------------------------
    with op.get_context().autocommit_block():
        for name, table, columns, unique in _INDEXES:
            op.execute(
                f"CREATE {'UNIQUE ' if unique else ''}INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({columns})"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _table, _columns, _unique in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")

    for name, _expr in _CONTEST_ATTEMPT_CHECKS:
        op.execute(f"ALTER TABLE contest_attempts DROP CONSTRAINT IF EXISTS ck_contest_attempts_{name}")

    op.drop_constraint("uq_registration_window_singleton", "registration_windows", type_="unique")
    op.drop_column("registration_windows", "singleton")

    op.drop_constraint(_fk_name("contest_certificates", "contest_id", "contests"), "contest_certificates", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("contest_certificates", "contest_id", "contests"),
        "contest_certificates", "contests", ["contest_id"], ["id"], ondelete="CASCADE",
    )
    op.alter_column("contest_certificates", "contest_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)

    op.drop_constraint(_fk_name("certificates", "course_id", "courses"), "certificates", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("certificates", "course_id", "courses"),
        "certificates", "courses", ["course_id"], ["id"], ondelete="CASCADE",
    )
    op.alter_column("certificates", "course_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_column("certificates", "course_title")
