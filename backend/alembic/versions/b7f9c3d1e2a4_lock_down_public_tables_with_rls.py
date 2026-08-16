"""enforce RLS on public tables

Revision ID: b7f9c3d1e2a4
Revises: a3d5e8f0c2b7
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7f9c3d1e2a4"
down_revision = "a3d5e8f0c2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The application uses its server-side database role for all data access.
    # Public/hosted API roles must not receive direct table access. RLS is
    # enabled on every public table and a restrictive deny policy is added so
    # future permissive policies cannot accidentally expose rows through a
    # direct PostgREST/API path.
    op.execute(
        """
        DO $$
        DECLARE
            r record;
        BEGIN
            FOR r IN
                SELECT c.oid::regclass AS table_ref
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
            LOOP
                EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', r.table_ref);
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_policies p
                    WHERE p.schemaname = 'public'
                      AND p.tablename = split_part(r.table_ref::text, '.', 2)
                      AND p.policyname = 'deny_direct_api_access'
                ) THEN
                    EXECUTE format(
                        'CREATE POLICY deny_direct_api_access ON %s AS RESTRICTIVE FOR ALL TO PUBLIC USING (false) WITH CHECK (false)',
                        r.table_ref
                    );
                END IF;
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            r record;
        BEGIN
            FOR r IN
                SELECT c.oid::regclass AS table_ref
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
            LOOP
                EXECUTE format(
                    'DROP POLICY IF EXISTS deny_direct_api_access ON %s',
                    r.table_ref
                );
                EXECUTE format('ALTER TABLE %s DISABLE ROW LEVEL SECURITY', r.table_ref);
            END LOOP;
        END $$;
        """
    )
