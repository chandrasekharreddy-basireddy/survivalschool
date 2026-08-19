from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_verified_user
from app.models.challenge import DailyChallenge, DailyChallengeAttempt
from app.models.gamification import Streak
from app.models.user import User
from app.schemas.challenge import (
    DailyChallengeAttemptOut,
    DailyChallengeHistoryEntryOut,
    DailyChallengeOut,
    DailyChallengeQuestionOut,
    DailyChallengeSubmit,
)
from app.services.daily_challenge_service import (
    get_my_attempt,
    get_or_create_todays_challenge,
    get_question_for_challenge,
    submit_attempt,
)

router = APIRouter(prefix="/daily-challenge", tags=["daily-challenge"])


async def _current_streak_days(db: AsyncSession, student_id) -> int:
    streak = (await db.execute(select(Streak).where(Streak.student_id == student_id))).scalar_one_or_none()
    return streak.current_streak_days if streak else 0


async def _build_out(db: AsyncSession, user: User, challenge: DailyChallenge) -> DailyChallengeOut:
    question = await get_question_for_challenge(db, challenge)
    attempt = await get_my_attempt(db, user.id, challenge.id)

    my_attempt = None
    if attempt is not None:
        correct_option_ids = [o.id for o in question.options if o.is_correct]
        my_attempt = DailyChallengeAttemptOut(
            is_correct=attempt.is_correct,
            points_awarded=attempt.points_awarded,
            selected_option_ids=list(attempt.selected_option_ids),
            correct_option_ids=correct_option_ids,
        )

    return DailyChallengeOut(
        id=challenge.id,
        challenge_date=challenge.challenge_date,
        question=DailyChallengeQuestionOut.model_validate(question),
        already_attempted=attempt is not None,
        my_attempt=my_attempt,
        current_streak_days=await _current_streak_days(db, user.id),
    )


@router.get("/today", response_model=DailyChallengeOut)
async def get_todays_challenge(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    challenge = await get_or_create_todays_challenge(db)
    await db.commit()
    out = await _build_out(db, user, challenge)
    return out


@router.post("/today/attempt", response_model=DailyChallengeOut)
async def submit_todays_challenge(
    payload: DailyChallengeSubmit,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    challenge = await get_or_create_todays_challenge(db)
    await submit_attempt(db, user=user, challenge=challenge, selected_option_ids=payload.selected_option_ids)
    await db.commit()
    return await _build_out(db, user, challenge)


@router.get("/history", response_model=list[DailyChallengeHistoryEntryOut])
async def my_challenge_history(
    limit: int = Query(30, le=100),
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(DailyChallenge.challenge_date, DailyChallengeAttempt.is_correct, DailyChallengeAttempt.points_awarded, DailyChallengeAttempt.created_at)
            .join(DailyChallengeAttempt, DailyChallengeAttempt.challenge_id == DailyChallenge.id)
            .where(DailyChallengeAttempt.student_id == user.id)
            .order_by(DailyChallenge.challenge_date.desc())
            .limit(limit)
        )
    ).all()
    return [
        DailyChallengeHistoryEntryOut(challenge_date=r[0], is_correct=r[1], points_awarded=r[2], answered_at=r[3])
        for r in rows
    ]
