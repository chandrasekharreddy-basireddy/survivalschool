#!/usr/bin/env python
"""Real, one-time maintenance script: wipes every user account (and anything
that references a user via a foreign key -- sessions, refresh tokens, email
verifications, enrollments, submissions, audit log rows tied to a user, etc.)
so the app can be tested from a genuinely clean slate.

Deliberately NOT wired into any API endpoint -- this is destructive and is
meant to be run once, by hand, against a specific database, by someone who
consciously chose to do it (Render's dashboard Shell tab, or a local shell
pointed at the target DATABASE_URL). It requires explicit confirmation and
prints exactly what it's about to do before doing it.

RBAC data (roles/permissions/badges) is NOT touched -- only the `users`
table and anything TRUNCATE ... CASCADE pulls in via real foreign keys.

Usage:
    python -m scripts.reset_all_accounts --yes-really-delete-all-accounts
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.database import AsyncSessionLocal


async def main():
    if "--yes-really-delete-all-accounts" not in sys.argv:
        print(
            "This deletes EVERY user account and everything that references a user "
            "(sessions, tokens, enrollments, submissions, etc.) from the real "
            "database this script is pointed at.\n\n"
            "Re-run with --yes-really-delete-all-accounts to actually do it.",
            file=sys.stderr,
        )
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        # TRUNCATE ... CASCADE is a real database-level cascade -- it follows
        # actual foreign key constraints, not just what the ORM's Python
        # relationships happen to model, so this is safe even if some FK
        # isn't mirrored in a SQLAlchemy relationship() somewhere.
        await db.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        await db.commit()

    print("All user accounts (and everything that references them) have been deleted.")
    print("Roles, permissions, and badges were left intact -- no re-seed needed.")


if __name__ == "__main__":
    asyncio.run(main())
