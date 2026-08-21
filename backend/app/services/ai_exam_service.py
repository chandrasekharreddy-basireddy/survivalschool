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
from app.core.runtime import spawn_background_task
from app.models.contest import Contest, ContestAttempt
from app.models.exam_platform import Topic, TopicDifficultyEvaluation
from app.models.user import User
from app.services.ai_provider import get_ai_provider
from app.services.ai_question_service import (
    find_or_create_subject,
    find_or_create_topic,
    generate_and_persist_questions,
)
from app.services.cache_service import bump_cache_version
from app.services.difficulty_service import MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM
from app.services.question_validation_service import QuestionValidationError
from app.services.registration_service import ai_exam_registration_is_open, get_or_create_window

logger = structlog.get_logger("survivalschool.ai_exam")

IST = ZoneInfo("Asia/Kolkata")
AI_WEEKLY_SINGLE_COUNT = 40
AI_WEEKLY_MULTIPLE_COUNT = 10
AI_WEEKLY_DURATION_SECONDS = 7200  # 2 hours
AI_WEEKLY_SLOT_HOUR = 14  # Saturday 14:00-16:00 IST
# Zero tolerance: a tab switch, a fullscreen exit, a copy/paste, a devtools
# attempt — any single integrity event auto-submits the attempt immediately
# with zero credit for whatever's left unanswered. See
# contests.py::contest_integrity_event / _force_finalize_contest_attempt.
AI_WEEKLY_MAX_INTEGRITY_VIOLATIONS = 1


def _upcoming_saturday_slot(now_ist: datetime) -> tuple[datetime, datetime, str]:
    days_ahead = (5 - now_ist.weekday()) % 7  # Saturday = 5
    if days_ahead == 0 and now_ist.hour >= AI_WEEKLY_SLOT_HOUR:
        days_ahead = 7
    target_date = (now_ist + timedelta(days=days_ahead)).date()
    starts_at = datetime.combine(target_date, datetime.min.time(), tzinfo=IST).replace(hour=AI_WEEKLY_SLOT_HOUR)
    ends_at = starts_at + timedelta(seconds=AI_WEEKLY_DURATION_SECONDS)
    return starts_at, ends_at, target_date.isoformat()


async def _generate_ai_weekly_questions_in_background(contest_id: uuid.UUID, topic: Topic) -> None:
    """Runs detached from the registration request that created the
    contest — see the asyncio.create_task call site in
    get_or_create_ai_weekly_contest. Writes question_ids onto the contest
    once generation lands; if it fails, the contest is left with an empty
    question_ids and start_contest_attempt's own guard below catches that
    rather than serving a broken/empty exam."""
    try:
        question_ids = await generate_and_persist_questions(topic, AI_WEEKLY_SINGLE_COUNT, AI_WEEKLY_MULTIPLE_COUNT)
    except QuestionValidationError as exc:
        logger.error("ai_weekly_generation_failed_validation", topic_id=str(topic.id), error=str(exc))
        return
    except Exception:
        logger.error("ai_weekly_generation_failed", topic_id=str(topic.id), exc_info=True)
        return

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        contest = await db.get(Contest, contest_id)
        if contest is not None:
            contest.question_ids = [str(q) for q in question_ids]
            await db.commit()


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

    contest = Contest(
        title=f"AI Weekly Exam — {topic.name}", description=f"50 questions (40 single-answer + 10 multi-select) on {topic.name}.",
        contest_type="ai_weekly", occurrence_key=occurrence_key, is_auto_generated=True, created_by=None,
        starts_at=starts_at.astimezone(UTC), ends_at=ends_at.astimezone(UTC), duration_seconds=AI_WEEKLY_DURATION_SECONDS,
        # Filled in by the background task kicked off below once generation
        # lands — NOT awaited inline here. Registration opens Thursday for
        # a Saturday exam, so there's always a multi-day gap before anyone
        # could actually start it (start_contest_attempt rejects any
        # attempt before contest.starts_at); generating 50 questions from a
        # real AI provider easily exceeds the frontend's/gunicorn's ~30s
        # request timeout, which was blocking registration itself (the
        # exact bug reported for elimination battles' smaller 18-question
        # pool — same root cause, same fix).
        question_ids=[], top_n_awarded=3, status="open",
        fullscreen_required=True, integrity_monitoring_enabled=True, max_integrity_violations=AI_WEEKLY_MAX_INTEGRITY_VIOLATIONS,
    )
    try:
        async with db.begin_nested():
            db.add(contest)
            await db.flush()
    except IntegrityError:
        # Lost the race to another concurrent registration for the same
        # topic/week. No generation has been kicked off yet at this point
        # (that happens below, only for the winning contest row), so
        # there's nothing wasted to clean up — just re-read the winner's row.
        contest = (await db.execute(select(Contest).where(Contest.occurrence_key == occurrence_key))).scalar_one()
        await bump_cache_version("contests_list")
        return contest

    spawn_background_task(_generate_ai_weekly_questions_in_background(contest.id, topic))
    await bump_cache_version("contests_list")
    return contest


async def register_for_ai_weekly_exam(db: AsyncSession, user: User, subject_name: str, topic_name: str) -> ContestAttempt:
    subject_name, topic_name = subject_name.strip(), topic_name.strip()
    if not subject_name or not topic_name:
        raise ValidationAppError("Both subject and topic are required.")

    window = await get_or_create_window(db)
    if not ai_exam_registration_is_open(datetime.now(UTC), window.override_until):
        raise ConflictError("AI Weekly Exam registration is closed. It opens every Thursday (IST).")

    subject = await find_or_create_subject(db, subject_name)
    topic = await find_or_create_topic(db, subject.id, topic_name)
    topic_id = topic.id

    # Always re-evaluated live — never trusted from a prior check-topic call
    # — since a freely-typed topic has no pre-existing question bank a
    # formula could score against. See ai_provider.py::evaluate_topic_scope.
    assessment = await get_ai_provider().evaluate_topic_scope(subject_name, topic_name)
    await db.execute(
        TopicDifficultyEvaluation.__table__.update()
        .where(TopicDifficultyEvaluation.topic_id == topic_id, TopicDifficultyEvaluation.is_current.is_(True))
        .values(is_current=False)
    )
    db.add(TopicDifficultyEvaluation(
        topic_id=topic_id, difficulty_percent=assessment.difficulty_percent, formula_version="ai-realtime-v1",
        reason=assessment.reason, sample_size=0,
    ))
    # Commit here regardless of outcome: the subject/topic rows must be
    # durably visible to other connections before get_or_create_ai_weekly_contest
    # below, which persists AI-generated questions through a SEPARATE
    # AsyncSessionLocal() session (see ai_question_service.generate_and_persist_questions) —
    # that session cannot see this one's uncommitted work, so an insert
    # referencing a subject/topic created-but-not-yet-committed here would
    # fail its foreign key constraint.
    await db.commit()
    if assessment.difficulty_percent < MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM or not assessment.is_appropriate_scope:
        raise ValidationAppError(
            f"This topic isn't eligible yet: {assessment.reason}",
            details={
                "difficulty_percent": assessment.difficulty_percent,
                "is_appropriate_scope": assessment.is_appropriate_scope,
                "min_difficulty_percent": MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM,
            },
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
