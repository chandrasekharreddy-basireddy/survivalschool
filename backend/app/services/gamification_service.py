"""All XP, streaks, and badge awards are computed and persisted here — server
side only (spec section 16: "All points and achievements must be calculated
and validated server-side.")."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import Achievement, Badge, PointsLedger, Streak

POINTS_LESSON_COMPLETE = 10
POINTS_QUIZ_PASS = 25
POINTS_EXAM_PASS = 100
POINTS_COURSE_COMPLETE = 150


async def award_points(db: AsyncSession, student_id: uuid.UUID, amount: int, reason: str, reference_id: uuid.UUID | None = None) -> None:
    db.add(PointsLedger(student_id=student_id, amount=amount, reason=reason, reference_id=reference_id))
    await db.flush()


async def get_total_points(db: AsyncSession, student_id: uuid.UUID) -> int:
    from sqlalchemy import func
    result = await db.execute(select(func.coalesce(func.sum(PointsLedger.amount), 0)).where(PointsLedger.student_id == student_id))
    return int(result.scalar_one())


async def record_daily_activity(db: AsyncSession, student_id: uuid.UUID) -> Streak:
    result = await db.execute(select(Streak).where(Streak.student_id == student_id))
    streak = result.scalar_one_or_none()
    today = datetime.now(timezone.utc).date()

    if streak is None:
        streak = Streak(student_id=student_id, current_streak_days=1, longest_streak_days=1,
                         last_activity_date=datetime.now(timezone.utc))
        db.add(streak)
        await db.flush()
        return streak

    last_date = streak.last_activity_date.date() if streak.last_activity_date else None
    if last_date == today:
        return streak
    if last_date == today - timedelta(days=1):
        streak.current_streak_days += 1
    else:
        streak.current_streak_days = 1
    streak.longest_streak_days = max(streak.longest_streak_days, streak.current_streak_days)
    streak.last_activity_date = datetime.now(timezone.utc)
    await db.flush()
    return streak


async def evaluate_and_award_badges(db: AsyncSession, student_id: uuid.UUID, event: str, context: dict) -> list[Badge]:
    """Very small, explicit rule engine — deliberately not a generic DSL, so every
    rule is auditable code, not opaque config."""
    awarded: list[Badge] = []
    candidates: list[str] = []

    if event == "lesson_complete" and context.get("is_first_lesson"):
        candidates.append("first_lesson")
    if event == "quiz_pass" and context.get("score_percent") == 100:
        candidates.append("perfect_quiz")
    if event == "course_complete":
        candidates.append("course_finisher")
    if event == "streak" and context.get("current_streak_days") == 7:
        candidates.append("week_streak")
    if event == "streak" and context.get("current_streak_days") == 30:
        candidates.append("month_streak")

    for code in candidates:
        badge = (await db.execute(select(Badge).where(Badge.criteria_code == code))).scalar_one_or_none()
        if badge is None:
            continue
        existing = (await db.execute(
            select(Achievement).where(Achievement.student_id == student_id, Achievement.badge_id == badge.id)
        )).scalar_one_or_none()
        if existing is None:
            db.add(Achievement(student_id=student_id, badge_id=badge.id))
            await award_points(db, student_id, 20, reason="badge", reference_id=badge.id)
            awarded.append(badge)
    await db.flush()
    return awarded
