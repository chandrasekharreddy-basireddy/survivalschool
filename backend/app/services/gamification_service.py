"""All XP, streaks, and badge awards are computed and persisted here — server
side only (spec section 16: "All points and achievements must be calculated
and validated server-side.")."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import Achievement, Badge, PointsLedger, Streak
from app.services.cache_service import bump_cache_version

POINTS_LESSON_COMPLETE = 10
POINTS_QUIZ_PASS = 25
POINTS_EXAM_PASS = 100
POINTS_COURSE_COMPLETE = 150


async def award_points(db: AsyncSession, student_id: uuid.UUID, amount: int, reason: str, reference_id: uuid.UUID | None = None) -> None:
    db.add(PointsLedger(student_id=student_id, amount=amount, reason=reason, reference_id=reference_id))
    await db.flush()
    # Every point-award path (quiz/exam pass, contest finish/top-3,
    # lesson/course complete, badges) funnels through here, so invalidating
    # the global leaderboard cache in this one place covers every write path
    # without needing to remember it at each of the 7 call sites.
    await bump_cache_version("gamification_leaderboard")


async def get_total_points(db: AsyncSession, student_id: uuid.UUID) -> int:
    from sqlalchemy import func
    result = await db.execute(select(func.coalesce(func.sum(PointsLedger.amount), 0)).where(PointsLedger.student_id == student_id))
    return int(result.scalar_one())


def _apply_todays_activity(streak: Streak, today) -> None:
    last_date = streak.last_activity_date.date() if streak.last_activity_date else None
    if last_date == today:
        return
    if last_date == today - timedelta(days=1):
        streak.current_streak_days += 1
    else:
        streak.current_streak_days = 1
    streak.longest_streak_days = max(streak.longest_streak_days, streak.current_streak_days)
    streak.last_activity_date = datetime.now(timezone.utc)


async def record_daily_activity(db: AsyncSession, student_id: uuid.UUID) -> Streak:
    """Two real callers can race here now (a lesson completion and a daily
    challenge answer landing back-to-back for the same student — see
    app/services/daily_challenge_service.py). This is a genuine
    read-modify-write: without locking, two concurrent requests can both
    read the same current_streak_days, both compute "+1", and the second
    UPDATE silently overwrites the first (a lost update, under-counting the
    streak). `SELECT ... FOR UPDATE` serializes concurrent updates to the
    same row within the DB itself, so the second request's read only
    happens after the first's write commits. The insert path (no Streak row
    yet) has a separate race — two concurrent first-ever activities for the
    same student both trying to INSERT — handled the same SAVEPOINT-then-
    catch-IntegrityError way the badge-award race is handled below."""
    today = datetime.now(timezone.utc).date()

    result = await db.execute(select(Streak).where(Streak.student_id == student_id).with_for_update())
    streak = result.scalar_one_or_none()

    if streak is not None:
        _apply_todays_activity(streak, today)
        await db.flush()
        return streak

    try:
        async with db.begin_nested():
            streak = Streak(student_id=student_id, current_streak_days=1, longest_streak_days=1,
                             last_activity_date=datetime.now(timezone.utc))
            db.add(streak)
            await db.flush()
        return streak
    except IntegrityError:
        # Lost the create race — another concurrent request inserted this
        # student's Streak row first. Lock and apply today's activity to
        # that row instead of erroring.
        result = await db.execute(select(Streak).where(Streak.student_id == student_id).with_for_update())
        streak = result.scalar_one()
        _apply_todays_activity(streak, today)
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
        if existing is not None:
            continue

        # The select-then-insert above has a race window: two concurrent
        # requests evaluating the same badge for the same student (e.g. two
        # quiz submissions completing at the same instant) can both see
        # "not yet awarded" and both try to insert. The database's unique
        # constraint on (student_id, badge_id) is the real guard; a SAVEPOINT
        # here means the request that loses the race only rolls back its own
        # badge insert, not the whole transaction — so the quiz/exam result,
        # points ledger entries, and everything else this request already
        # did still commit normally.
        try:
            async with db.begin_nested():
                db.add(Achievement(student_id=student_id, badge_id=badge.id))
                await award_points(db, student_id, 20, reason="badge", reference_id=badge.id)
                await db.flush()
        except IntegrityError:
            continue
        awarded.append(badge)
    return awarded
