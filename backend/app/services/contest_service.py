"""Platform-wide contest scheduling, question selection, and finalization.

Design constraints, deliberate:
- Contest questions are always drawn from validated Question rows
  (is_validated=True) — either instructor-authored, or AI-generated and
  then passed through question_validation_service before that flag is set.
  Certificates get issued off these results, so the answer key must be
  something that actually passed structural/answer-count validation, not
  raw unchecked model output. (Courses/instructor ownership no longer
  gate this bank — see ai_exam_service.py for the AI Weekly Exam's own
  generation path, which is a separate, always-AI-generated flow by
  design since it needs a fresh set every week.)
- Auto-generated occurrences (weekly Sat/Sun morning+evening IST, monthly)
  are idempotent via Contest.occurrence_key's unique constraint — the worker
  polls every 5 minutes and simply skips creating a contest whose occurrence
  key already exists (see check_and_create_scheduled_contests below).
- Finalization (ranking + top-N certificates + points) only ever runs once
  per contest: finalize_contest() re-fetches the Contest row with
  with_for_update before checking finalized_at, so two overlapping callers
  (the scheduler's own polling tick racing an admin's manual finalize) can't
  both pass the check. Certificate inserts get an additional, independent
  backstop from a SAVEPOINT+IntegrityError pattern around the unique
  constraint, since a certificate could otherwise already exist from a
  previous partial run.
"""
from __future__ import annotations

import random
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import Question
from app.models.contest import Contest, ContestAnswer, ContestAttempt, ContestCertificate
from app.models.user import User
from app.services.audit_service import record_audit_event
from app.services.cache_service import bump_cache_version, cache_delete
from app.services.contest_certificate_service import certificate_expiry
from app.services.gamification_service import award_points
from app.services.notification_service import create_notification
from app.services.scoring_service import summarize_attempt

logger = structlog.get_logger("survivalschool.contests")

IST = ZoneInfo("Asia/Kolkata")

WEEKLY_SLOTS = [
    (5, 9, 0, 90, "sat-am", "weekly_morning"),
    (5, 18, 0, 90, "sat-pm", "weekly_evening"),
    (6, 9, 0, 90, "sun-am", "weekly_morning"),
    (6, 18, 0, 90, "sun-pm", "weekly_evening"),
]
MONTHLY_SLOT = (6, 9, 0, 120)
WEEKLY_QUESTION_COUNT = 15
MONTHLY_QUESTION_COUNT = 30
CONTEST_ATTEMPT_DURATION_SECONDS = 1800
POINTS_CONTEST_FINISH = 15
POINTS_CONTEST_TOP3 = 50


async def select_contest_questions(db: AsyncSession, count: int) -> list[uuid.UUID]:
    rows = (await db.execute(select(Question.id).where(Question.is_validated.is_(True)))).scalars().all()
    if not rows:
        return []
    return random.sample(list(rows), min(count, len(rows)))


def _this_or_last_occurrence_date(now_ist: datetime, weekday: int) -> date:
    days_since = (now_ist.weekday() - weekday) % 7
    return (now_ist - timedelta(days=days_since)).date()


def _first_sunday_of_month(now_ist: datetime) -> date:
    first_of_month = now_ist.date().replace(day=1)
    offset = (6 - first_of_month.weekday()) % 7
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
        return None
    await bump_cache_version("contests_list")
    return contest


async def check_and_create_scheduled_contests(db: AsyncSession) -> list[Contest]:
    now_ist = datetime.now(IST)
    created: list[Contest] = []
    for weekday, hour, minute, duration_minutes, slot_key, contest_type in WEEKLY_SLOTS:
        occurrence_date = _this_or_last_occurrence_date(now_ist, weekday)
        slot_start = datetime.combine(occurrence_date, datetime.min.time(), tzinfo=IST).replace(hour=hour, minute=minute)
        slot_end = slot_start + timedelta(minutes=duration_minutes)
        if slot_start > now_ist or now_ist > slot_start + timedelta(hours=6):
            continue
        occurrence_key = f"weekly-{slot_key}-{occurrence_date.isoformat()}"
        contest = await _create_if_missing(
            db, occurrence_key=occurrence_key,
            title=f"Weekend Challenge — {occurrence_date.strftime('%A %b %d')} {'Morning' if 'am' in slot_key else 'Evening'}",
            description="A weekly platform-wide contest — top 3 win a certificate.",
            contest_type=contest_type, starts_at=slot_start, ends_at=slot_end,
            question_count=WEEKLY_QUESTION_COUNT,
        )
        if contest:
            created.append(contest)

    _, m_hour, m_minute, m_duration_minutes = MONTHLY_SLOT
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


async def _finalize_abandoned_attempt(db: AsyncSession, attempt: ContestAttempt) -> None:
    """Same auto-grade-and-submit shape as contests.py's
    _force_finalize_contest_attempt (triggered there by hitting the
    integrity-violation cap) — here triggered by the contest itself ending
    while the attempt was still "in_progress" because the student never
    called POST /attempts/{id}/submit (closed the tab, connection dropped,
    simply forgot). Without this, that attempt just stayed "in_progress"
    forever: excluded from finalize_contest's ranking query below (which
    only selects status=="submitted"), never graded, never notified,
    silently absent from the leaderboard — the "abandoned" status has
    existed in ContestAttempt's own CheckConstraint since the schema was
    written, but nothing ever set it. Grading whatever was actually
    answered (rather than leaving it un-scored) treats a student who
    answered 40 of 50 questions before losing their connection the same
    way an integrity-cap auto-submit already treats a partial attempt —
    consistent, and fairer than discarding their work entirely."""
    rows = (await db.execute(select(ContestAnswer).where(ContestAnswer.attempt_id == attempt.id))).scalars().all()
    answered_qids = {row.question_id for row in rows}
    points_earned = sum(row.points_awarded for row in rows)
    remaining_qids = [uuid.UUID(q) for q in attempt.question_order if uuid.UUID(q) not in answered_qids]
    if remaining_qids:
        questions_by_id = {
            q.id: q for q in (await db.execute(
                select(Question).where(Question.id.in_(remaining_qids)).options(selectinload(Question.options))
            )).scalars().all()
        }
        for qid in remaining_qids:
            question = questions_by_id.get(qid)
            if question is None:
                continue
            db.add(ContestAnswer(attempt_id=attempt.id, question_id=qid, selected_option_ids=[], is_correct=False, points_awarded=0))
    all_qids = [uuid.UUID(q) for q in attempt.question_order]
    all_questions = (await db.execute(select(Question).where(Question.id.in_(all_qids)))).scalars().all()
    points_possible = sum(q.points for q in all_questions)

    now = datetime.now(UTC)
    score_percent, _ = summarize_attempt(points_earned, points_possible, 0)
    attempt.points_earned = points_earned
    attempt.points_possible = points_possible
    attempt.score_percent = score_percent
    attempt.status = "submitted"
    attempt.submitted_at = now
    attempt.time_taken_seconds = int((now - attempt.started_at).total_seconds())
    await record_audit_event(
        db, actor_id=None, action="contest.auto_submitted_deadline", resource_type="contest_attempt",
        resource_id=str(attempt.id), metadata={"score_percent": score_percent, "answered_count": len(answered_qids)},
    )


async def finalize_contest(db: AsyncSession, contest: Contest) -> Contest:
    # Re-fetch with a row lock before the idempotency check: the caller may
    # have loaded `contest` via a plain SELECT (e.g. the scheduler's own
    # listing query, or the admin manual-finalize endpoint), and without a
    # lock here, two callers racing the same just-ended contest (a manual
    # admin trigger landing at the same moment as the next scheduler tick)
    # can both read finalized_at as None and both award every participant's
    # points twice — the certificate insert is separately protected by a
    # unique constraint, but the points-award loop below has no such
    # backstop. with_for_update makes the second caller block until the
    # first commits, at which point its own finalized_at check (right below)
    # correctly short-circuits it.
    locked = await db.get(Contest, contest.id, with_for_update=True)
    if locked is None or locked.finalized_at is not None:
        return locked or contest
    contest = locked

    # The contest is ending right now — any attempt still "in_progress"
    # never will call POST /attempts/{id}/submit on its own. Auto-grade and
    # submit each one before the ranking query below, which only ever
    # looks at status=="submitted" — without this step those attempts
    # would just stay "in_progress" forever, ungraded and absent from the
    # leaderboard.
    stuck_attempts = (await db.execute(
        select(ContestAttempt).where(ContestAttempt.contest_id == contest.id, ContestAttempt.status == "in_progress")
    )).scalars().all()
    for stuck in stuck_attempts:
        await _finalize_abandoned_attempt(db, stuck)

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
                contest_title=contest.title, contest_type=contest.contest_type, score_percent=attempt.score_percent or 0,
                expires_at=certificate_expiry(),
            )
            try:
                async with db.begin_nested():
                    db.add(cert)
                    await db.flush()
            except IntegrityError:
                pass
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
    contest.finalized_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(contest)
    await bump_cache_version("contests_list")
    await bump_cache_version("ai_weekly_wins_leaderboard")
    await cache_delete(f"contest:{contest.id}:leaderboard")
    logger.info("contest_finalized", contest_id=str(contest.id), participants=len(attempts))
    return contest


async def check_and_finalize_contests(db: AsyncSession) -> list[Contest]:
    now = datetime.now(UTC)
    pending = (await db.execute(select(Contest).where(Contest.status != "closed", Contest.ends_at < now))).scalars().all()
    finalized = []
    for contest in pending:
        finalized.append(await finalize_contest(db, contest))
    return finalized
