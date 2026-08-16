"""merge certificate and scheduling RLS migration heads

Revision ID: f3a6b7c8d9e0
Revises: e1f4a6b8c2d0, e7c4f1a2b9d0

The contest certificate lifecycle migration and the V2 scheduling RLS
migration both branch from c9d4e7a1f6b8. This merge revision restores a
single Alembic head without changing either migration's schema work.
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
