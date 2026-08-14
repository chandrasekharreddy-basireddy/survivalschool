from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_verified_user, require_permission
from app.models.assessment import Question
from app.models.contest import Contest, ContestAnswer, ContestAttempt, ContestCertificate
from app.models.user import User
from app.schemas.assessment import QuestionPublicOut
from app.schemas.contest import (
    ContestAttemptStartOut,
    ContestCertificateOut,
    ContestCreate,
    ContestOut,
    ContestResultOut,
    ContestSubmit,
    LeaderboardEntryOut,
)
from app.services.audit_service import record_audit_event
from app.services.cache_service import (
    bump_cache_version,
    cache_delete,
    cache_get_json,
    cache_get_versioned,
    cache_set_json,
    cache_set_versioned,
)
from app.services.contest_service import finalize_contest
from app.services.scoring_service import grade_answer, summarize_attempt

# Contest lists change rarely (only on create/finalize) but are read on
# every visit to the public contests page — worth a short cache. The
# leaderboard changes on every submission during a live contest, so it gets
# its own much shorter TTL, invalidated directly on submit.
_CONTESTS_LIST_TTL = 15
_LEADERBOARD_TTL = 5

router = APIRouter(prefix="/contests", tags=["contests"])


def _contest_out(contest: Contest) -> ContestOut:
    return ContestOut(
        id=contest.id, title=contest.title, description=contest.description, contest_type=contest.contest_type,
        is_auto_generated=contest.is_auto_generated, starts_at=contest.starts_at, ends_at=contest.ends_at,
        duration_seconds=contest.duration_seconds, top_n_awarded=contest.top_n_awarded, status=contest.status,
        question_count=len(contest.question_ids),
    )


@router.get("", response_model=list[ContestOut])
async def list_contests(status_filter: str | None = Query(None, alias="status"), db: AsyncSession = Depends(get_db)):
    """Public — browsing contests (and the countdown to the next one) doesn't
    require an account; only participating does."""
    cache_key = f"status={status_filter or ''}"
    cached = await cache_get_versioned("contests_list", cache_key)
    if cached is not None:
        return cached

    stmt = select(Contest).order_by(Contest.starts_at.desc())
    if status_filter:
        stmt = stmt.where(Contest.status == status_filter)
    contests = (await db.execute(stmt)).scalars().all()
    out = [_contest_out(c) for c in contests]
    await cache_set_versioned("contests_list", cache_key, [o.model_dump(mode="json") for o in out], _CONTESTS_LIST_TTL)
    return out


@router.get("/upcoming", response_model=list[ContestOut])
async def upcoming_contests(db: AsyncSession = Depends(get_db)):
    """The next open/scheduled contests, soonest first — powers the
    countdown widget. Public."""
    cached = await cache_get_versioned("contests_list", "upcoming")
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    contests = (await db.execute(
        select(Contest).where(Contest.status.in_(["scheduled", "open"]), Contest.ends_at > now)
        .order_by(Contest.starts_at.asc()).limit(5)
    )).scalars().all()
    out = [_contest_out(c) for c in contests]
    await cache_set_versioned("contests_list", "upcoming", [o.model_dump(mode="json") for o in out], _CONTESTS_LIST_TTL)
    return out


@router.post("", response_model=ContestOut, status_code=201)
async def create_contest(payload: ContestCreate, user: User = Depends(require_permission("contests.manage")), db: AsyncSession = Depends(get_db)):
    contest = Contest(
        title=payload.title, description=payload.description, contest_type="custom",
        is_auto_generated=False, created_by=user.id, starts_at=payload.starts_at, ends_at=payload.ends_at,
        duration_seconds=payload.duration_seconds, question_ids=[str(q) for q in payload.question_ids],
        top_n_awarded=payload.top_n_awarded, status="open",
    )
    db.add(contest)
    await record_audit_event(db, actor_id=user.id, action="contest.create", resource_type="contest")
    await db.commit()
    await db.refresh(contest)
    await bump_cache_version("contests_list")
    return _contest_out(contest)


@router.get("/{contest_id}", response_model=ContestOut)
async def get_contest(contest_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    contest = await db.get(Contest, contest_id)
    if contest is None:
        raise NotFoundError("Contest not found.")
    return _contest_out(contest)


def _leaderboard_cache_key(contest_id: uuid.UUID) -> str:
    return f"contest:{contest_id}:leaderboard"


@router.get("/{contest_id}/leaderboard", response_model=list[LeaderboardEntryOut])
async def contest_leaderboard(contest_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Public, live — shows every attempt submitted so far, ranked. During an
    open contest this updates in real time as students finish; after
    finalization it matches the permanent rank/certificate record.

    Cached for a few seconds: this is the single hottest read during a live
    contest (every participant's client polls it), and the underlying query
    joins and sorts every submitted attempt on every request. A 5-second
    staleness window is invisible to a human refreshing a leaderboard, and
    the cache is invalidated immediately on every submit anyway, so the
    window only matters for concurrent requests arriving within the same
    few seconds."""
    cached = await cache_get_json(_leaderboard_cache_key(contest_id))
    if cached is not None:
        return cached

    contest = await db.get(Contest, contest_id)
    if contest is None:
        raise NotFoundError("Contest not found.")
    rows = (await db.execute(
        select(ContestAttempt, User.full_name)
        .join(User, User.id == ContestAttempt.student_id)
        .where(ContestAttempt.contest_id == contest_id, ContestAttempt.status == "submitted")
        .order_by(ContestAttempt.score_percent.desc(), ContestAttempt.time_taken_seconds.asc(), ContestAttempt.submitted_at.asc())
    )).all()
    out = [
        LeaderboardEntryOut(
            rank=attempt.rank or idx, student_id=attempt.student_id, student_name=name,
            score_percent=attempt.score_percent or 0, time_taken_seconds=attempt.time_taken_seconds,
        )
        for idx, (attempt, name) in enumerate(rows, start=1)
    ]
    await cache_set_json(_leaderboard_cache_key(contest_id), [o.model_dump(mode="json") for o in out], _LEADERBOARD_TTL)
    return out


@router.post("/{contest_id}/attempts", response_model=ContestAttemptStartOut, status_code=201)
async def start_contest_attempt(contest_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    contest = await db.get(Contest, contest_id)
    if contest is None or contest.status != "open":
        raise NotFoundError("Contest not found or not currently open.")

    now = datetime.now(timezone.utc)
    if now < contest.starts_at:
        raise ConflictError("This contest hasn't started yet.")
    if now > contest.ends_at:
        raise ConflictError("This contest window has closed.")

    existing = (await db.execute(
        select(ContestAttempt).where(ContestAttempt.contest_id == contest_id, ContestAttempt.student_id == user.id)
    )).scalar_one_or_none()
    if existing:
        if existing.status == "in_progress":
            remaining = (existing.server_deadline_at - now).total_seconds()
            return ContestAttemptStartOut(
                attempt_id=existing.id, server_deadline_at=existing.server_deadline_at,
                remaining_seconds=max(0, int(remaining)), resumed=True,
            )
        raise ConflictError("You've already competed in this contest — one attempt per student.")

    question_ids = [uuid.UUID(q) for q in contest.question_ids]
    import random
    random.shuffle(question_ids)
    deadline = min(now + timedelta(seconds=contest.duration_seconds), contest.ends_at)

    attempt = ContestAttempt(
        contest_id=contest_id, student_id=user.id, question_order=[str(q) for q in question_ids],
        server_deadline_at=deadline,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return ContestAttemptStartOut(
        attempt_id=attempt.id, server_deadline_at=deadline,
        remaining_seconds=int((deadline - now).total_seconds()), resumed=False,
    )


@router.get("/attempts/{attempt_id}/questions", response_model=list[QuestionPublicOut])
async def get_contest_attempt_questions(attempt_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    attempt = await db.get(ContestAttempt, attempt_id)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    question_ids = [uuid.UUID(q) for q in attempt.question_order]
    result = await db.execute(select(Question).where(Question.id.in_(question_ids)).options(selectinload(Question.options)))
    questions = {q.id: q for q in result.scalars().all()}
    return [QuestionPublicOut.model_validate(questions[q]) for q in question_ids if q in questions]


@router.post("/attempts/{attempt_id}/submit", response_model=ContestResultOut)
async def submit_contest_attempt(attempt_id: uuid.UUID, payload: ContestSubmit, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    # Same with_for_update race-closing pattern as quizzes/exams — see the
    # matching comment there for why the lock (not just the status check) is
    # what actually prevents a double-submit from double-scoring.
    attempt = await db.get(ContestAttempt, attempt_id, with_for_update=True)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.status != "in_progress":
        return ContestResultOut.model_validate(attempt)

    now = datetime.now(timezone.utc)
    late = now > attempt.server_deadline_at

    points_earned, points_possible = 0, 0
    for ans in payload.answers:
        question = (await db.execute(
            select(Question).where(Question.id == ans.question_id).options(selectinload(Question.options))
        )).scalar_one_or_none()
        if question is None:
            continue
        sel = [] if late else [str(i) for i in ans.selected_option_ids]
        is_correct, points = grade_answer(question, sel, None if late else ans.text_answer)
        points_earned += points
        points_possible += question.points
        db.add(ContestAnswer(
            attempt_id=attempt.id, question_id=question.id, selected_option_ids=sel,
            text_answer=ans.text_answer, is_correct=is_correct, points_awarded=points,
        ))

    score_percent, _ = summarize_attempt(points_earned, points_possible, 0)
    attempt.points_earned = points_earned
    attempt.points_possible = points_possible
    attempt.score_percent = score_percent
    attempt.status = "submitted"
    attempt.submitted_at = now
    attempt.time_taken_seconds = int((now - attempt.started_at).total_seconds())

    await record_audit_event(db, actor_id=user.id, action="contest.attempt_submitted", resource_type="contest_attempt", resource_id=str(attempt.id))
    await db.commit()
    await db.refresh(attempt)
    await cache_delete(_leaderboard_cache_key(attempt.contest_id))
    return ContestResultOut.model_validate(attempt)


@router.get("/me/certificates", response_model=list[ContestCertificateOut])
async def my_contest_certificates(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    certs = (await db.execute(
        select(ContestCertificate).where(ContestCertificate.student_id == user.id).order_by(ContestCertificate.issued_at.desc())
    )).scalars().all()
    return certs


@router.get("/certificates/verify/{certificate_number}", response_model=ContestCertificateOut)
async def verify_contest_certificate(certificate_number: str, db: AsyncSession = Depends(get_db)):
    """Public, unauthenticated — same spirit as /certificates/verify/{number}."""
    cert = (await db.execute(
        select(ContestCertificate).where(ContestCertificate.certificate_number == certificate_number)
    )).scalar_one_or_none()
    if cert is None:
        raise NotFoundError("Certificate not found.")
    return cert


@router.post("/{contest_id}/finalize", response_model=ContestOut)
async def manual_finalize_contest(contest_id: uuid.UUID, user: User = Depends(require_permission("contests.manage")), db: AsyncSession = Depends(get_db)):
    """Manual trigger for an admin (or a test) — the worker does this
    automatically every 5 minutes, but this lets an admin close out a
    contest immediately rather than waiting for the next tick."""
    contest = await db.get(Contest, contest_id)
    if contest is None:
        raise NotFoundError("Contest not found.")
    if datetime.now(timezone.utc) < contest.ends_at:
        raise ConflictError("This contest's window hasn't closed yet.")
    contest = await finalize_contest(db, contest)
    return _contest_out(contest)
