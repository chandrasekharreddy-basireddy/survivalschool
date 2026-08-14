"""One shared question a day, scored server-side, feeding the same streak
tracked by lesson completion (app/services/gamification_service.py). Picking
"today's" question and recording an attempt both have real concurrency
windows (two requests racing to create today's row, or a student
double-submitting) — both handled with the same SAVEPOINT-then-catch pattern
already used for badge awarding, so a losing request's own insert rolls back
without touching whatever else that request already committed.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.assessment import Question
from app.models.challenge import DailyChallenge, DailyChallengeAttempt
from app.models.user import User
from app.services.gamification_service import (
    award_points,
    evaluate_and_award_badges,
    record_daily_activity,
)

POINTS_DAILY_CHALLENGE = 15

# How many of the most recent daily challenges to avoid repeating, if the
# bank is big enough to avoid a repeat that far back.
_NO_REPEAT_WINDOW = 30


async def get_or_create_todays_challenge(db: AsyncSession) -> DailyChallenge:
    today = datetime.now(timezone.utc).date()
    existing = (
        await db.execute(select(DailyChallenge).where(DailyChallenge.challenge_date == today))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    recent_question_ids = (
        await db.execute(
            select(DailyChallenge.question_id)
            .order_by(DailyChallenge.challenge_date.desc())
            .limit(_NO_REPEAT_WINDOW)
        )
    ).scalars().all()

    stmt = select(Question.id).where(Question.question_type.in_(["single", "true_false"]))
    if recent_question_ids:
        stmt = stmt.where(Question.id.notin_(recent_question_ids))
    candidate_ids = list((await db.execute(stmt)).scalars().all())

    if not candidate_ids:
        # Question bank too small to avoid a repeat today — allow one rather
        # than have the feature simply stop working.
        candidate_ids = list(
            (
                await db.execute(select(Question.id).where(Question.question_type.in_(["single", "true_false"])))
            ).scalars().all()
        )
    if not candidate_ids:
        raise NotFoundError("No questions available yet for a daily challenge.")

    question_id = random.choice(candidate_ids)

    try:
        async with db.begin_nested():
            challenge = DailyChallenge(challenge_date=today, question_id=question_id)
            db.add(challenge)
            await db.flush()
    except IntegrityError:
        # Another concurrent request created today's row first — that's the
        # real one now; fetch and return it instead of erroring.
        existing = (
            await db.execute(select(DailyChallenge).where(DailyChallenge.challenge_date == today))
        ).scalar_one()
        return existing

    return challenge


async def get_question_for_challenge(db: AsyncSession, challenge: DailyChallenge) -> Question:
    result = await db.execute(
        select(Question).where(Question.id == challenge.question_id).options(selectinload(Question.options))
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise NotFoundError("Today's challenge question is no longer available.")
    return question


async def get_my_attempt(db: AsyncSession, student_id: uuid.UUID, challenge_id: uuid.UUID) -> DailyChallengeAttempt | None:
    return (
        await db.execute(
            select(DailyChallengeAttempt).where(
                DailyChallengeAttempt.student_id == student_id,
                DailyChallengeAttempt.challenge_id == challenge_id,
            )
        )
    ).scalar_one_or_none()


async def submit_attempt(
    db: AsyncSession, *, user: User, challenge: DailyChallenge, selected_option_ids: list[uuid.UUID]
) -> DailyChallengeAttempt:
    if await get_my_attempt(db, user.id, challenge.id) is not None:
        raise ValidationAppError("You've already answered today's challenge.")

    question = await get_question_for_challenge(db, challenge)
    correct_option_ids = {str(o.id) for o in question.options if o.is_correct}
    submitted_ids = {str(oid) for oid in selected_option_ids}
    is_correct = submitted_ids == correct_option_ids and len(submitted_ids) > 0
    points = POINTS_DAILY_CHALLENGE if is_correct else 0

    try:
        async with db.begin_nested():
            attempt = DailyChallengeAttempt(
                student_id=user.id,
                challenge_id=challenge.id,
                selected_option_ids=[str(oid) for oid in selected_option_ids],
                is_correct=is_correct,
                points_awarded=points,
            )
            db.add(attempt)
            await db.flush()
    except IntegrityError:
        raise ValidationAppError("You've already answered today's challenge.") from None

    if is_correct:
        await award_points(db, user.id, points, reason="daily_challenge", reference_id=challenge.id)

    # Answering today's challenge counts as real daily activity, exactly
    # like completing a lesson — a student who only ever does the daily
    # challenge still legitimately builds a streak.
    streak = await record_daily_activity(db, user.id)
    await evaluate_and_award_badges(db, user.id, "streak", {"current_streak_days": streak.current_streak_days})

    return attempt
