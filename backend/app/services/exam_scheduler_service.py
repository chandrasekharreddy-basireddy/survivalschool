from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import Exam, ExamAttempt, ExamAnswer, Question, QuestionOption
from app.models.lms import Course
from app.models.scheduling import ScheduledExamConfig
from app.models.user import User
from app.services.ai_provider import get_ai_provider
from app.services.certificate_service import issue_certificate
from app.services.scoring_service import grade_answer, summarize_attempt

logger = structlog.get_logger("survivalschool.exam_scheduler")

IST = ZoneInfo("Asia/Kolkata")


def _occurrence_key(now_ist: datetime, time_slot: str) -> str:
    return f"{now_ist.date().isoformat()}:{time_slot}"


def _slot_minutes(time_slot: str) -> tuple[int, int]:
    hour, minute = (int(part) for part in time_slot.split(":", 1))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid time slot: {time_slot}")
    return hour, minute


# Weekend AI-exam grid: Saturday (5) and Sunday (6), morning and evening IST.
WEEKEND_DAYS = (5, 6)
WEEKEND_SLOTS = ("09:00", "18:00")


async def ensure_weekend_schedules(db: AsyncSession) -> int:
    """Guarantee every published course has the four weekend AI-exam slots
    (Sat/Sun x morning/evening IST). Idempotent: the unique constraint on
    (day_of_week, time_slot, course_id) means re-running only fills gaps, so
    this can run on every worker tick and newly published courses pick up their
    weekend exams automatically, with no manual scheduling.
    """
    courses = (await db.execute(
        select(Course).where(Course.is_published.is_(True), Course.deleted_at.is_(None))
    )).scalars().all()
    if not courses:
        return 0

    existing = {
        (c.course_id, c.day_of_week, c.time_slot)
        for c in (await db.execute(select(ScheduledExamConfig))).scalars().all()
    }

    created = 0
    for course in courses:
        for day in WEEKEND_DAYS:
            for slot in WEEKEND_SLOTS:
                if (course.id, day, slot) in existing:
                    continue
                db.add(ScheduledExamConfig(
                    day_of_week=day,
                    time_slot=slot,
                    duration_minutes=60,
                    question_count=10,
                    auto_certificate_top_n=3,
                    course_id=course.id,
                    difficulty="mixed",
                    title_prefix="Weekend AI Exam",
                    is_active=True,
                ))
                created += 1
    if created:
        try:
            await db.commit()
        except IntegrityError:
            # Another process (the standalone worker, if it's ever deployed
            # alongside this in-process scheduler, or a second gunicorn
            # worker racing the same tick) inserted the same
            # (day_of_week, time_slot, course_id) row first — the unique
            # constraint on ScheduledExamConfig caught it. Nothing lost: the
            # gap is filled either way, so just roll back this attempt.
            await db.rollback()
            logger.info("weekend_schedule_creation_raced", attempted=created)
            return 0
    return created


async def create_due_scheduled_exams(db: AsyncSession, now: datetime | None = None) -> list[Exam]:
    current = (now or datetime.now(timezone.utc)).astimezone(IST)
    configs = (await db.execute(select(ScheduledExamConfig).where(ScheduledExamConfig.is_active.is_(True)))).scalars().all()
    created: list[Exam] = []
    provider = get_ai_provider()

    for config in configs:
        if config.day_of_week != current.weekday():
            continue
        try:
            hour, minute = _slot_minutes(config.time_slot)
        except ValueError:
            continue
        slot = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if current < slot or current >= slot + timedelta(minutes=10):
            continue
        key = _occurrence_key(current, config.time_slot)
        if config.last_occurrence_key == key:
            continue

        course = await db.get(Course, config.course_id)
        if course is None:
            continue
        # Re-check the course is still live: it may have been unpublished or
        # soft-deleted after this schedule was created (ensure_weekend_schedules
        # only filters at config-creation time). Without this, an unpublished
        # course could still get a fresh weekend exam auto-created and
        # auto-published every week forever.
        if not course.is_published or course.deleted_at is not None:
            continue

        # Each config's work runs inside its own SAVEPOINT: a flaky AI call or
        # a malformed generated question for ONE config must not discard the
        # exams already generated (flushed but not yet committed) for every
        # other due config in this same tick — begin_nested() lets us roll
        # back just this config's partial work and continue the loop.
        try:
            async with db.begin_nested():
                generated = await provider.generate_questions(course.title, config.question_count)
                question_ids: list[str] = []
                for item in generated:
                    question = Question(course_id=course.id, prompt=item.prompt, question_type="single", points=1)
                    db.add(question)
                    await db.flush()
                    for idx, (text, is_correct) in enumerate(item.options):
                        db.add(QuestionOption(question_id=question.id, text=text, is_correct=is_correct, order_index=idx))
                    question_ids.append(str(question.id))

                starts_at = slot.astimezone(timezone.utc)
                ends_at = starts_at + timedelta(minutes=config.duration_minutes)
                exam = Exam(
                    course_id=course.id,
                    title=f"{config.title_prefix}: {course.title}",
                    time_limit_seconds=config.duration_minutes * 60,
                    max_attempts=1,
                    pass_score_percent=70,
                    is_published=True,
                    available_from=starts_at,
                    available_until=ends_at,
                    question_ids=question_ids,
                    fullscreen_required=True,
                    integrity_monitoring_enabled=True,
                    max_integrity_violations=3,
                    is_ai_scheduled=True,
                    auto_certificate_top_n=config.auto_certificate_top_n,
                )
                db.add(exam)
                await db.flush()
                config.last_occurrence_key = key
        except Exception:
            # Leave last_occurrence_key untouched so this occurrence is
            # retried on the next tick (still within the 10-minute window)
            # instead of being silently skipped for the whole slot.
            logger.warning("scheduled_exam_creation_failed", course_id=str(config.course_id), time_slot=config.time_slot, exc_info=True)
            continue
        created.append(exam)

    await db.commit()
    return created


async def finalize_expired_scheduled_exams(db: AsyncSession, now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    attempts = (await db.execute(
        select(ExamAttempt)
        .join(Exam, Exam.id == ExamAttempt.exam_id)
        .where(Exam.is_ai_scheduled.is_(True), ExamAttempt.status == "in_progress", ExamAttempt.server_deadline_at < current)
    )).scalars().all()
    finalized = 0

    for attempt in attempts:
        exam = await db.get(Exam, attempt.exam_id)
        if exam is None:
            continue
        rows = (await db.execute(select(ExamAnswer).where(ExamAnswer.attempt_id == attempt.id))).scalars().all()
        answers = {row.question_id: row for row in rows}
        points_earned = 0
        points_possible = 0
        for qid in [uuid.UUID(q) for q in attempt.question_order]:
            question = (await db.execute(select(Question).where(Question.id == qid).options(selectinload(Question.options)))).scalar_one_or_none()
            if question is None:
                continue
            points_possible += question.points
            row = answers.get(qid)
            selected = row.selected_option_ids if row else []
            text = row.text_answer if row else None
            correct, points = grade_answer(question, selected, text)
            points_earned += points
            if row:
                row.is_correct = correct
                row.points_awarded = points

        score, passed = summarize_attempt(points_earned, points_possible, exam.pass_score_percent)
        attempt.points_earned = points_earned
        attempt.points_possible = points_possible
        attempt.score_percent = score
        attempt.passed = passed
        attempt.status = "submitted"
        attempt.submitted_at = current
        attempt.flagged_events = attempt.flagged_events + [{"type": "auto_submit_expired", "at": current.isoformat()}]
        finalized += 1

    await db.commit()
    return finalized


async def issue_scheduled_exam_certificates(db: AsyncSession) -> int:
    exams = (await db.execute(select(Exam).where(Exam.is_ai_scheduled.is_(True), Exam.auto_certificate_top_n > 0))).scalars().all()
    issued = 0
    current = datetime.now(timezone.utc)
    for exam in exams:
        if exam.available_until is None or exam.available_until > current:
            continue
        attempts = (await db.execute(
            select(ExamAttempt).where(ExamAttempt.exam_id == exam.id, ExamAttempt.status == "submitted", ExamAttempt.passed.is_(True)).order_by(ExamAttempt.score_percent.desc(), ExamAttempt.submitted_at.asc()).limit(exam.auto_certificate_top_n)
        )).scalars().all()
        course = await db.get(Course, exam.course_id)
        if course is None:
            continue
        for attempt in attempts:
            student = await db.get(User, attempt.student_id)
            if student is None:
                continue
            await issue_certificate(db, student, course)
            issued += 1
        await db.commit()
    return issued
