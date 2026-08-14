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

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.gamification import Badge
from app.models.lms import Course, CourseSection, Lesson
from app.models.user import Permission, Role, User
from app.security.passwords import hash_password

settings = get_settings()

PERMISSIONS = [
    "users.read", "users.update", "users.delete",
    "courses.create", "courses.read", "courses.update", "courses.delete",
    "lessons.manage",
    "quiz.create", "quiz.manage",
    "exam.manage",
    "results.view",
    "analytics.view",
    "chat.moderate",
    "notifications.manage",
    "system.manage",
    "certificates.manage",
    "files.upload",
]

ROLE_PERMISSIONS = {
    "STUDENT": ["files.upload"],
    "INSTRUCTOR": ["courses.create", "courses.read", "courses.update", "lessons.manage",
                   "quiz.create", "quiz.manage", "exam.manage", "results.view", "files.upload"],
    "MODERATOR": ["chat.moderate", "users.read"],
    "SUPPORT": ["users.read", "notifications.manage"],
    "ADMIN": ["users.read", "users.update", "courses.create", "courses.read", "courses.update",
              "courses.delete", "lessons.manage", "quiz.create", "quiz.manage", "exam.manage",
              "results.view", "analytics.view", "chat.moderate", "notifications.manage",
              "certificates.manage", "files.upload", "system.manage"],
    "SUPER_ADMIN": PERMISSIONS,  # also implicitly bypasses all checks — see dependencies.py
}

BADGES = [
    ("first_lesson", "First Steps", "Complete your first lesson", "footprints"),
    ("perfect_quiz", "Perfectionist", "Score 100% on a quiz", "star"),
    ("course_finisher", "Course Finisher", "Complete a full course", "trophy"),
    ("week_streak", "Week Warrior", "Maintain a 7-day learning streak", "flame"),
    ("month_streak", "Unstoppable", "Maintain a 30-day learning streak", "medal"),
]


async def seed_rbac():
    async with AsyncSessionLocal() as db:
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

        for code, name, desc, icon in [(c, n, d, i) for c, n, d, i in BADGES]:
            pass
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
        instructor = await ensure_user("instructor@survivalschool.dev", "Ian Instructor", ["INSTRUCTOR"])
        await ensure_user("student@survivalschool.dev", "Sam Student", ["STUDENT"])

        course = (await db.execute(select(Course).where(Course.slug == "python-foundations"))).scalar_one_or_none()
        if course is None:
            course = Course(
                title="Python Foundations", slug="python-foundations",
                description="Learn Python from first principles through hands-on MCQ challenges.",
                difficulty="beginner", is_published=True, instructor_id=instructor.id, estimated_hours=6,
            )
            db.add(course)
            await db.flush()
            section = CourseSection(course_id=course.id, title="Getting Started", order_index=0)
            db.add(section)
            await db.flush()
            db.add(Lesson(section_id=section.id, title="What is Python?", content_type="article",
                           content_body="Python is a high-level, readable programming language...",
                           order_index=0, duration_minutes=8))
            db.add(Lesson(section_id=section.id, title="Variables and Types", content_type="article",
                           content_body="Variables in Python are dynamically typed...",
                           order_index=1, duration_minutes=10))

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
