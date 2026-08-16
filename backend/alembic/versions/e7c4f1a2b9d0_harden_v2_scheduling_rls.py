"""Harden V2 scheduling tables with the same server-only RLS posture.

Revision ID: e7c4f1a2b9d0
Revises: f2a7c9e1b4d6
"""
from alembic import op

revision = "e7c4f1a2b9d0"
down_revision = "f2a7c9e1b4d6"
branch_labels = None
depends_on = None


def _lock_table(table_name: str) -> None:
    op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS deny_direct_api_access ON public.{table_name}")
    op.execute(
        f"CREATE POLICY deny_direct_api_access ON public.{table_name} "
        "AS RESTRICTIVE FOR ALL TO anon, authenticated "
        "USING (false) WITH CHECK (false)"
    )


def upgrade() -> None:
    _lock_table("registration_windows")
    _lock_table("scheduled_exam_configs")


def downgrade() -> None:
    for table_name in ("registration_windows", "scheduled_exam_configs"):
        op.execute(f"DROP POLICY IF EXISTS deny_direct_api_access ON public.{table_name}")
        op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")
