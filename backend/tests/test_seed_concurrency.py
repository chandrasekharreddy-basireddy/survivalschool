"""
Real reproduction + regression test for the production race condition found
in seed_rbac() on 2026-08-15: multiple gunicorn workers booting concurrently
against a freshly-migrated (empty permissions/roles/badges) database both ran
the old check-then-insert seeding logic at once and collided on
iix_permissions_code`, crashing one worker's startup with
asyncpg.exceptions.UniqueViolationError.

This test reproduces that exact scenario for real: it empties the relevant
tables, then invokes seed_rbac() concurrently via asyncio.gather (mirroring
concurrent process startup), and asserts it does not raise and leaves the
database in the correct, fully-seeded state. The fix under test is the
pg_advisory_xact_lock serialization added to seed_rbac() in app/seed.py.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.gamification import Badge
from app.models.user import Permission, Role
from app.seed import BADGES, PERMISSIONS, ROLE_PERMISSIONS, seed_rbac

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _empty_rbac_tables():
    async with AsyncSessionLocal() as db:
        # role_permissions is an association table cleared automatically by
        # cascade when roles are deleted (see model relationship config);
        # delete roles first, then permissions and badges.
        await db.execute(delete(Role))
        await db.execute(delete(Permission))
        await db.execute(delete(Badge))
        await db.commit()


async def test_concurrent_seed_rbac_does_not_raise_and_seeds_correctly():
    await _empty_rbac_tables()

    # Real concurrent invocation -- this is what two gunicorn workers booting
    # at the same moment against an empty DB actually do. Before the
    # pg_advisory_xact_lock fix, this reliably raised
    # asyncpg.exceptions.UniqueViolationError on ix_permissions_code.
    results = await asyncio.gather(seed_rbac(), seed_rbac(), seed_rbac(), return_exceptions=True)

    exceptions = [r for r in results if isinstance(r, Exception)]
    assert exceptions == [], f"seed_rbac() raised under concurrency: {exceptions}"

    async with AsyncSessionLocal() as db:
        perms = (await db.execute(select(Permission))).scalars().all()
        roles = (await db.execute(select(Role))).scalars().all()
        badges = (await db.execute(select(Badge))).scalars().all()

    assert {p.code for p in perms} == set(PERMISSIONS)
    assert len(perms) == len(PERMISSIONS)  # no duplicate rows from the race
    assert {r.name for r in roles} == set(ROLE_PERMISSIONS.keys())
    assert len(roles) == len(ROLE_PERMISSIONS)
    assert {b.code for b in badges} == {c for c, *_ in BADGES}
    assert len(badges) == len(BADGES)


async def test_seed_rbac_still_idempotent_when_run_sequentially_after_concurrent_run():
    # After the concurrent run above already seeded everything, a normal
    # subsequent boot (single worker, data already present) must still be a
    # safe no-op -- this is the original idempotency guarantee and must not
    # regress from the locking change.
    await seed_rbac()

    async with AsyncSessionLocal() as db:
        perms = (await db.execute(select(Permission))).scalars().all()
        roles = (await db.execute(select(Role))).scalars().all()

    assert len(perms) == len(PERMISSIONS)
    assert len(roles) == len(ROLE_PERMISSIONS)
