"""Platform-wide contest scheduling, question selection, and finalization.

Design constraints, deliberate:
- Contest questions are always drawn from real, instructor-authored Question
  rows belonging to published courses — never AI-generated. Certificates get
  issued off these results, so the answer key must be something a human
  instructor actually vetted, not something a language model produced.
- Auto-generated occurrences (weekly Sat/Sun morning+evening IST, monthly)
  are idempotent via Contest.occurrence_key's unique constraint — the worker
  polls every 5 minutes and simply skips creating a contest whose occurrence
  key already exists (see check_and_create_scheduled_contests below).
- Finalization (ranking + top-N certificates + points) only ever runs once
  per contest, guarded by `finalized_at` and the same SAVEPOINT+IntegrityError
  pattern used by certificate_service/gamification_service elsewhere in this
  codebase, in case two worker ticks somehow overlap.
"""
from __future__ import annotations

import random
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Question
from app.models.contest import Contest, ContestAttempt, ContestCertificate
from app.models.lms import Course
from app.models.user import User
from app.services.gamification_service import award_points
from app.services.notification_service import create_notification

logger = structlog.get_logger("survivalschool.contests")

IST = ZoneInfo("Asia/Kolkata")

# (weekday: Mon=0..Sun=6, hour, minute, duration_minutes, slot_key, contest_type)
WEEKLY_SLOTS = [
    (5, 9, 0, 90, "sat-am", "weekly_morning"),
    (5, 18, 0, 90, "sat-pm", "weekly_evening"),
    (6, 9, 0, 90, "sun-am", "weekly_morning"),
    (6, 18, 0, 90, "sun-pm", "weekly_evening"),
]
MONTHLY_SLOT = (6, 9, 0, 120)  # first Sunday of the month, 9:00 IST, 2-hour window, bigger contest

WEEKLY_QUESTION_COUNT = 15
MONTHLY_QUESTION_COUNT = 30
CONTEST_ATTEMPT_DURATION_SECONDS = 1800  # 30 minutes per student once they start

POINTS_CONTEST_FINISH = 15
POINTS_CONTEST_TOP3 = 50


async def select_contest_questions(db: AsyncSession, count: int) -> list[uuid.UUID]:
    """Random sample of real questions from published, non-deleted courses.
    Real content only — no AI generation anywhere near this path (see
    module docstring)."""
    rows = (await db.execute(
        select(Question.id)
        .join(Course, Course.id == Question.course_id)
        .where(Course.is_published.is_(True), Course.deleted_at.is_(None))
    )).scalars().all()
    if not rows:
        return []
    sample_size = min(count, len(rows))
    return random.sample(list(rows), sample_size)


def _next_occurrence_date(now_ist: datetime, weekday: int) -> date:
    days_ahead = (weekday - now_ist.weekday()) % 7
    return (now_ist + timedelta(days=days_ahead)).date()


def _this_or_last_occurrence_date(now_ist: datetime, weekday: int) -> date:
    """The most recent date (today or earlier this week) matching `weekday`."""
    days_since = (now_ist.weekday() - weekday) % 7
    return (now_ist - timedelta(days=days_since)).date()


def _first_sunday_of_month(now_ist: datetime) -> date:
    first_of_month = now_ist.date().replace(day=1)
    offset = (6 - first_of_month.weekday()) % 7  # 6 = Sunday
    return first_of_month + timedelta(days=offset)


async def _create_if_missing(
    db: AsyncSession, *, occurrence_key: str, title: str, description: str, contest_type: str,
    starts_at: datetime, ends_at: datetime, question_count: int,
) -> Contest | None:
    existing = (await db.execute(select(Contest).where(Contest.occurrence_key == occurrence_key))).scalar_one_or_none()
    if existing is not None:
        return None

    question_ids = await select_contest_questions(db, question_count)
    if not question_ids:
        logger.warning("contest_skipped_no_questions", occurrence_key=occurrence_key)
        return None

    contest = Contest(
        title=title, description=description, contest_type=contest_type,
        occurrence_key=occurrence_key, is_auto_generated=True, created_by=None,
        starts_at=starts_at, ends_at=ends_at, duration_seconds=CONTEST_ATTEMPT_DURATION_SECONDS,
        question_ids=[str(q) for q in question_ids], status="open",
    )
    try:
        async with db.begin_nested():
            db.add(contest)
            await db.flush()
    except IntegrityError:
        # Lost a race with another worker tick / replica creating the same
        # occurrence at the same time — completely normal, not an error.
        return None
    return contest


async def check_and_create_scheduled_contests(db: AsyncSession) -> list[Contest]:
    """Idempotent — safe to call every worker tick. Creates any weekly/monthly
    contest occurrence whose scheduled start has just arrived (or recently
    passed, e.g. if the worker was briefly down) and doesn't exist yet."""
    now_ist = datetime.now(IST)
    created: list[Contest] = []

    for weekday, hour, minute, duration_minutes, slot_key, contest_type in WEEKLY_SLOTS:
        occurrence_date = _this_or_last_occurrence_date(now_ist, weekday)
        slot_start = datetime.combine(occurrence_date, datetime.min.time(), tzinfo=IST).replace(hour=hour, minute=minute)
        slot_end = slot_start + timedelta(minutes=duration_minutes)
        # Only create once we've actually reached the slot's start time, and
        # only within a reasonable catch-up window (don't backfill contests
        # from days ago if the worker was down for a while).
        if slot_start > now_ist or now_ist > slot_start + timedelta(hours=6):
            continue
        occurrence_key = f"weekly-{slot_key}-{occurrence_date.isoformat()}"
        contest = await _create_if_missing(
            db, occurrence_key=occurrence_key,
            title=f"Weekend Challenge — {occurrence_date.strftime('%A %b %d')} {'Morning' if 'am' in slot_key else 'Evening'}",
            description="A weekly platform-wide contest — real questions from published courses, top 3 win a certificate.",
            contest_type=contest_type, starts_at=slot_start, ends_at=slot_end,
            question_count=WEEKLY_QUESTION_COUNT,
        )
        if contest:
            created.append(contest)

    m_weekday, m_hour, m_minute, m_duration_minutes = MONTHLY_SLOT
    monthly_date = _first_sunday_of_month(now_ist)
    monthly_start = datetime.combine(monthly_date, datetime.min.time(), tzinfo=IST).replace(hour=m_hour, minute=m_minute)
    monthly_end = monthly_start + timedelta(minutes=m_duration_minutes)
    if monthly_start <= now_ist <= monthly_start + timedelta(hours=6):
        occurrence_key = f"monthly-{monthly_date.isoformat()}"
        contest = await _create_if_missing(
            db, occurrence_key=occurrence_key,
            title=f"Monthly Championship — {monthly_date.strftime('%B %Y')}",
            description="The big monthly platform-wide contest — larger question set, top 3 win a certificate.",
            contest_type="monthly", starts_at=monthly_start, ends_at=monthly_end,
            question_count=MONTHLY_QUESTION_COUNT,
        )
        if contest:
            created.append(contest)

    if created:
        await db.commit()
    return created


def _generate_contest_certificate_number() -> str:
    return f"SS-CONTEST-{secrets.token_hex(6).upper()}"


async def finalize_contest(db: AsyncSession, contest: Contest) -> Contest:
    """Ranks every submitted attempt (score desc, then time-taken asc as a
    tiebreak, then submitted_at asc as a final tiebreak), awards participation
    points to everyone who finished, and issues a real ContestCertificate to
    the top N. If fewer than N students actually competed, only that many
    certificates are issued — never fabricated placements."""
    if contest.finalized_at is not None:
        return contest

    attempts = (await db.execute(
        select(ContestAttempt)
        .where(ContestAttempt.contest_id == contest.id, ContestAttempt.status == "submitted")
        .order_by(ContestAttempt.score_percent.desc(), ContestAttempt.time_taken_seconds.asc(), ContestAttempt.submitted_at.asc())
    )).scalars().all()

    for idx, attempt in enumerate(attempts, start=1):
        attempt.rank = idx
        student = await db.get(User, attempt.student_id)
        if student is None:
            continue
        await award_points(db, student.id, POINTS_CONTEST_FINISH, reason="contest_finish", reference_id=contest.id)

        if idx <= contest.top_n_awarded:
            await award_points(db, student.id, POINTS_CONTEST_TOP3, reason="contest_top3", reference_id=contest.id)
            cert = ContestCertificate(
                certificate_number=_generate_contest_certificate_number(),
                contest_id=contest.id, student_id=student.id, rank=idx,
                contest_title=contest.title, score_percent=attempt.score_percent or 0,
            )
            try:
                async with db.begin_nested():
                    db.add(cert)
                    await db.flush()
            except IntegrityError:
                pass  # already issued (re-run safety)
            await create_notification(
                db, user=student, category="achievement",
                title=f"You placed #{idx} in {contest.title}!",
                body=f"Congratulations — you finished #{idx} with a score of {attempt.score_percent}%. Your certificate is ready.",
                link_url=f"/contests/{contest.id}",
                email_template="contest_result",
                email_context={"contest_title": contest.title, "rank": idx, "score_percent": attempt.score_percent},
            )
        else:
            await create_notification(
                db, user=student, category="assessment",
                title=f"Results are in for {contest.title}",
                body=f"You finished #{idx} of {len(attempts)} with a score of {attempt.score_percent}%.",
                link_url=f"/contests/{contest.id}",
            )

    contest.status = "closed"
    contest.finalized_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(contest)
    logger.info("contest_finalized", contest_id=str(contest.id), participants=len(attempts))
    return contest


async def check_and_finalize_contests(db: AsyncSession) -> list[Contest]:
    """Finds every contest whose window has closed but hasn't been ranked
    yet, and finalizes each. Safe to call every worker tick."""
    now = datetime.now(timezone.utc)
    pending = (await db.execute(
        select(Contest).where(Contest.status != "closed", Contest.ends_at < now)
    )).scalars().all()
    finalized = []
    for contest in pending:
        finalized.append(await finalize_contest(db, contest))
    return finalized
