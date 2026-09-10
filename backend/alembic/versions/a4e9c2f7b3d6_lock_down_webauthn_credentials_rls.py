"""Enable RLS on webauthn_credentials, missed by the table's own migration.

Every other table in this schema is locked with the same server-only
deny_direct_api_access policy (see b7f9c3d1e2a4 and e7c4f1a2b9d0) precisely
because this app talks to Postgres directly from the backend and never
through Supabase's PostgREST/client SDK layer -- so the anon/authenticated
API roles should never see any table. d3f6a9c2e7b1 (add_webauthn_credentials)
created this table without that step, leaving stored passkey public keys and
credential IDs reachable through the project's PostgREST endpoint with only
the public anon key. Closes that gap with the identical policy used
everywhere else in this schema.

Revision ID: a4e9c2f7b3d6
Revises: 3bf82d268141
"""
from __future__ import annotations

from alembic import op

revision: str = "a4e9c2f7b3d6"
down_revision: str | None = "3bf82d268141"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.webauthn_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS deny_direct_api_access ON public.webauthn_credentials")
    op.execute(
        "CREATE POLICY deny_direct_api_access ON public.webauthn_credentials "
        "AS RESTRICTIVE FOR ALL TO PUBLIC "
        "USING (false) WITH CHECK (false)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS deny_direct_api_access ON public.webauthn_credentials")
    op.execute("ALTER TABLE public.webauthn_credentials DISABLE ROW LEVEL SECURITY")
