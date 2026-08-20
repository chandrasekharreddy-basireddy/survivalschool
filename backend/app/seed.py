"""Idempotent seed script — safe to run multiple times.

Seeds: roles + permissions + role-permission grants, gamification badges, and
(development only) demo admin/instructor/student accounts with clearly
non-production passwords printed once to stdout (spec section 45: "Seed
scripts must clearly distinguish development from production.").

Usage: python -m app.seed [--with-demo-data]
"""
from __future__ import annotations

import asyncio
import secrets
import sys

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.gamification import Badge
from app.models.user import Permission, Role, User
from app.security.passwords import hash_password

settings = get_settings()

PERMISSIONS = [
    "users.read", "users.update", "users.delete",
    "quiz.create", "quiz.manage",
    "exam.manage",
    "results.view",
    "analytics.view",
    "chat.moderate",
    "notifications.manage",
    "system.manage",
    "certificates.manage",
    "files.upload",
    "contests.manage",
]

ROLE_PERMISSIONS = {
    "STUDENT": ["files.upload"],
    "INSTRUCTOR": ["quiz.create", "quiz.manage", "exam.manage", "results.view", "files.upload", "contests.manage"],
    "MODERATOR": ["chat.moderate", "users.read"],
    "SUPPORT": ["users.read", "notifications.manage"],
    "ADMIN": ["users.read", "users.update", "quiz.create", "quiz.manage", "exam.manage",
              "results.view", "analytics.view", "chat.moderate", "notifications.manage",
              "certificates.manage", "files.upload", "system.manage", "contests.manage"],
    "SUPER_ADMIN": PERMISSIONS,  # also implicitly bypasses all checks — see dependencies.py
}

BADGES = [
    ("perfect_quiz", "Perfectionist", "Score 100% on a quiz", "star"),
    ("week_streak", "Week Warrior", "Maintain a 7-day learning streak", "flame"),
    ("month_streak", "Unstoppable", "Maintain a 30-day learning streak", "medal"),
    ("battle_winner", "Last One Standing", "Win an elimination battle", "crown"),
]



# Arbitrary fixed key for a Postgres advisory lock used to serialize
# seed_rbac() across concurrently-starting processes (e.g. multiple gunicorn
# workers booting at once against a fresh/empty database). Any int64 works;
# this one has no special meaning. pg_advisory_xact_lock blocks the calling
# transaction until it can acquire the lock, and releases it automatically
# on commit/rollback -- no separate unlock call needed, and it can't leak.
_SEED_RBAC_LOCK_KEY = 918273645


async def seed_rbac():
    async with AsyncSessionLocal() as db:
        # Serialize concurrent seeders. Without this, two workers can both
        # SELECT a permission row, both see it missing, and both INSERT --
        # racing on the ix_permissions_code unique constraint
        # (UniqueViolationError). With the lock, the second worker blocks
        # here until the first one commits, then its own check-then-insert
        # reads find everything already present and it's a safe no-op.
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SEED_RBAC_LOCK_KEY})

        perm_by_code = {}
        for code in PERMISSIONS:
            existing = (await db.execute(select(Permission).where(Permission.code == code))).scalar_one_or_none()
            if existing is None:
                existing = Permission(code=code, description=code.replace(".", " ").title())
                db.add(existing)
                await db.flush()
            perm_by_code[code] = existing

        for role_name, perm_codes in ROLE_PERMISSIONS.items():
            role = (await db.execute(
                select(Role).where(Role.name == role_name).options(selectinload(Role.permissions))
            )).scalar_one_or_none()
            if role is None:
                role = Role(name=role_name, description=f"{role_name} role")
                db.add(role)
                await db.flush()
                await db.refresh(role, attribute_names=["permissions"])
            for code in perm_codes:
                perm = perm_by_code[code]
                if perm not in role.permissions:
                    role.permissions.append(perm)

        for code, name, desc, icon in BADGES:
            existing = (await db.execute(select(Badge).where(Badge.code == code))).scalar_one_or_none()
            if existing is None:
                db.add(Badge(code=code, name=name, description=desc, icon=icon, criteria_code=code))

        await db.commit()
    print("RBAC roles/permissions and gamification badges seeded.")


async def seed_demo_data():
    if settings.APP_ENV == "production":
        print("Refusing to seed demo data in production.", file=sys.stderr)
        return

    async with AsyncSessionLocal() as db:
        roles = {r.name: r for r in (await db.execute(select(Role).options(selectinload(Role.permissions)))).scalars().all()}
        demo_password = f"Demo!{secrets.token_hex(4)}A1"

        async def ensure_user(email: str, full_name: str, role_names: list[str]) -> User:
            existing = (await db.execute(
                select(User).where(User.email == email).options(selectinload(User.roles))
            )).scalar_one_or_none()
            if existing:
                return existing
            u = User(email=email, password_hash=hash_password(demo_password), full_name=full_name, is_email_verified=True)
            for rn in role_names:
                u.roles.append(roles[rn])
            db.add(u)
            await db.flush()
            return u

        await ensure_user("admin@survivalschool.dev", "Ada Admin", ["ADMIN"])
        await ensure_user("instructor@survivalschool.dev", "Ian Instructor", ["INSTRUCTOR"])
        await ensure_user("student@survivalschool.dev", "Sam Student", ["STUDENT"])
        await db.commit()

    print("Demo data seeded.")
    print("  admin@survivalschool.dev / instructor@survivalschool.dev / student@survivalschool.dev")
    print(f"  password: {demo_password}  (development only — never reused for production)")


async def main():
    await seed_rbac()
    if "--with-demo-data" in sys.argv:
        await seed_demo_data()


if __name__ == "__main__":
    asyncio.run(main())
