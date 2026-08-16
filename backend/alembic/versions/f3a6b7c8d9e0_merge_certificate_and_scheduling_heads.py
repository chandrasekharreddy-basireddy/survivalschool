"""merge certificate and scheduling RLS migration heads

Revision ID: f3a6b7c8d9e0
Revises: e1f4a6b8c2d0, e7c4f1a2b9d0

Both migrations intentionally branch from c9d4e7a1f6b8: one adds contest
certificate lifecycle fields and the other hardens the V2 scheduling tables
with server-only RLS. This merge revision restores a single Alembic head
without changing either migration's data/schema work.
"""
from typing import Sequence, Union

revision = "f3a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = ("e1f4a6b8c2d0", "e7c4f1a2b9d0")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
