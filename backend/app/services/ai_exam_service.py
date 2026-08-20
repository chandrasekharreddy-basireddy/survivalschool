"""The AI Weekly Exam: registration (Thursday-gated, subject+topic,
70%-difficulty-gated) through to a fixed 2-hour, 50-question (40 single +
10 multiple) exam every registrant sits in full — no elimination.

Each (topic, week) gets its own auto-generated Contest of
contest_type="ai_weekly", scheduled for the Saturday following the
Thursday registration window opens (14:00-16:00 IST, chosen to avoid the
existing weekly/monthly platform-contest slots at 09:00/18:00). Idempotent
per (topic, week) via Contest.occurrence_key, same pattern as the existing
weekly/monthly contests in contest_service.py.

Registration itself is a ContestAttempt row in status="registered" — see
the CHECK constraint comment on ContestAttempt in models/contest.py. The
same row later becomes the actual timed attempt when the student starts
it (contests.py::start_contest_attempt), so "you must register to take
this exam" falls out of the normal attempt lookup rather than a second
table to keep in sync.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.assessment import Question, QuestionOption
from app.models.contest import Contest, ContestAttempt
from app.models.exam_platform import Subject, Topic
from app.models.user import User
from app.services.ai_provider import get_ai_provider
from app.services.cache_service import bump_cache_version
from app.services.difficulty_service import (
    MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM,
    get_current_difficulty,
)
from app.services.question_validation_service import (
    QuestionValidationError,
    validate_generated_batch,
)
from app.services.registration_service import ai_exam_registration_is_open, get_or_create_window

logger = structlog.get_logger("survivalschool.ai_exam")

IST = ZoneInfo("Asia/Kolkata")
AI_WEEKLY_SINGLE_COUNT = 40
AI_WEEKLY_MULTIPLE_COUNT = 10
AI_WEEKLY_DURATION_SECONDS = 7200  # 2 hours
AI_WEEKLY_SLOT_HOUR = 14  # Saturday 14:00-16:00 IST


def _upcoming_saturday_slot(now_ist: datetime) -> tuple[datetime, datetime, str]:
    days_ahead = (5 - now_ist.weekday()) % 7  # Saturday = 5
    if days_ahead == 0 and now_ist.hour >= AI_WEEKLY_SLOT_HOUR:
        days_ahead = 7
    target_date = (now_ist + timedelta(days=days_ahead)).date()
    starts_at = datetime.combine(target_date, datetime.min.time(), tzinfo=IST).replace(hour=AI_WEEKLY_SLOT_HOUR)
    ends_at = starts_at + timedelta(seconds=AI_WEEKLY_DURATION_SECONDS)
    return starts_at, ends_at, target_date.isoformat()


async def _generate_and_persist_questions(topic: Topic) -> list[uuid.UUID]:
    provider = get_ai_provider()
    generated = await provider.generate_mixed_questions(topic.name, AI_WEEKLY_SINGLE_COUNT, AI_WEEKLY_MULTIPLE_COUNT)
    validate_generated_batch(generated)

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        question_ids: list[uuid.UUID] = []
        for gq in generated:
            question = Question(
                subject_id=topic.subject_id, topic_id=topic.id, prompt=gq.prompt,
                question_type=gq.question_type, is_ai_generated=True, is_validated=True,
            )
            db.add(question)
            await db.flush()
            for idx, (text, is_correct) in enumerate(gq.options):
                db.add(QuestionOption(question_id=question.id, text=text, is_correct=is_correct, order_index=idx))
            question_ids.append(question.id)
        await db.commit()
    return question_ids


async def get_or_create_ai_weekly_contest(db: AsyncSession, topic_id: uuid.UUID) -> Contest:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise NotFoundError("Topic not found.")
    now_ist = datetime.now(IST)
    starts_at, ends_at, week_key = _upcoming_saturday_slot(now_ist)
    occurrence_key = f"ai_weekly-{topic_id}-{week_key}"

    existing = (await db.execute(select(Contest).where(Contest.occurrence_key == occurrence_key))).scalar_one_or_none()
    if existing is not None:
        return existing

    try:
        question_ids = await _generate_and_persist_questions(topic)
    except QuestionValidationError as exc:
        logger.error("ai_weekly_generation_failed_validation", topic_id=str(topic_id), error=str(exc))
        raise ValidationAppError(f"Couldn't generate a valid exam for this topic: {exc}") from exc

    contest = Contest(
        title=f"AI Weekly Exam — {topic.name}", description=f"50 questions (40 single-answer + 10 multi-select) on {topic.name}.",
        contest_type="ai_weekly", occurrence_key=occurrence_key, is_auto_generated=True, created_by=None,
        starts_at=starts_at.astimezone(UTC), ends_at=ends_at.astimezone(UTC), duration_seconds=AI_WEEKLY_DURATION_SECONDS,
        question_ids=[str(q) for q in question_ids], top_n_awarded=3, status="open",
        fullscreen_required=True, integrity_monitoring_enabled=True, max_integrity_violations=3,
    )
    try:
        async with db.begin_nested():
            db.add(contest)
            await db.flush()
    except IntegrityError:
        # Lost the race to another concurrent registration for the same
        # topic/week — the questions we just generated are simply unused,
        # not a correctness problem (Question rows aren't scoped to one
        # contest). Re-read the winner's row.
        contest = (await db.execute(select(Contest).where(Contest.occurrence_key == occurrence_key))).scalar_one()
    await bump_cache_version("contests_list")
    return contest


async def register_for_ai_weekly_exam(db: AsyncSession, user: User, subject_id: uuid.UUID, topic_id: uuid.UUID) -> ContestAttempt:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise NotFoundError("Subject not found.")
    topic = await db.get(Topic, topic_id)
    if topic is None or topic.subject_id != subject_id:
        raise ValidationAppError("The selected topic does not belong to the selected subject.")

    window = await get_or_create_window(db)
    if not ai_exam_registration_is_open(datetime.now(UTC), window.override_until):
        raise ConflictError("AI Weekly Exam registration is closed. It opens every Thursday (IST).")

    evaluation = await get_current_difficulty(db, topic_id)
    if evaluation.difficulty_percent < MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM:
        raise ValidationAppError(
            f"This topic does not currently meet the minimum AI difficulty requirement "
            f"({evaluation.difficulty_percent}% < {MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM}%)."
        )

    contest = await get_or_create_ai_weekly_contest(db, topic_id)

    existing = (await db.execute(
        select(ContestAttempt).where(ContestAttempt.contest_id == contest.id, ContestAttempt.student_id == user.id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    attempt = ContestAttempt(
        contest_id=contest.id, student_id=user.id, status="registered",
        # Placeholder upper bound until the real 2-hour deadline is set at
        # actual start time (contests.py::start_contest_attempt) — never
        # left NULL, since the column is NOT NULL, but never used to grade
        # anything while status="registered".
        server_deadline_at=contest.ends_at,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt
