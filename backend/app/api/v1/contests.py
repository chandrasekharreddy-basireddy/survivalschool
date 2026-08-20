from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.database import get_db
from app.dependencies import get_client_ip, get_current_verified_user, require_permission
from app.models.assessment import Question
from app.models.contest import Contest, ContestAnswer, ContestAttempt, ContestCertificate
from app.models.user import User
from app.schemas.assessment import FlaggedAttemptOut, IntegrityEventIn, QuestionPublicOut
from app.schemas.contest import (
    AIWeeklyRegisterIn,
    AIWeeklyRegisterOut,
    ContestAttemptStartOut,
    ContestCertificateOut,
    ContestCertificatePublicOut,
    ContestCertificateRevokeOut,
    ContestCreate,
    ContestOut,
    ContestResultOut,
    ContestSubmit,
    LeaderboardEntryOut,
)
from app.services.ai_exam_service import register_for_ai_weekly_exam
from app.services.audit_service import record_audit_event
from app.services.cache_service import (
    bump_cache_version,
    cache_delete,
    cache_get_json,
    cache_get_versioned,
    cache_set_json,
    cache_set_versioned,
)
from app.services.contest_certificate_service import (
    generate_pdf_bytes,
    generate_qr_png_bytes,
    verification_url,
)
from app.services.contest_service import finalize_contest
from app.services.scoring_service import grade_answer, summarize_attempt

# Bounds flagged_events growth — a spammy or buggy client calling the
# integrity-event endpoint repeatedly can't grow an attempt's event log
# without limit. Ported from the old exam_security.py, now enforced
# against contest_attempts instead of the removed exam_attempts.
MAX_FLAGGED_EVENTS_PER_ATTEMPT = 200

_CONTESTS_LIST_TTL = 15
_LEADERBOARD_TTL = 5

router = APIRouter(prefix="/contests", tags=["contests"])


def _contest_out(contest: Contest) -> ContestOut:
    return ContestOut(
        id=contest.id, title=contest.title, description=contest.description, contest_type=contest.contest_type,
        is_auto_generated=contest.is_auto_generated, starts_at=contest.starts_at, ends_at=contest.ends_at,
        duration_seconds=contest.duration_seconds, top_n_awarded=contest.top_n_awarded, status=contest.status,
        question_count=len(contest.question_ids),
        fullscreen_required=contest.fullscreen_required, integrity_monitoring_enabled=contest.integrity_monitoring_enabled,
    )


def _contest_certificate_out(cert: ContestCertificate) -> ContestCertificateOut:
    return ContestCertificateOut(
        certificate_number=cert.certificate_number, contest_id=cert.contest_id,
        contest_title=cert.contest_title, rank=cert.rank, score_percent=cert.score_percent,
        issued_at=cert.issued_at, expires_at=cert.expires_at,
        revoked=cert.revoked_at is not None, verify_url=verification_url(cert.certificate_number),
    )


def _contest_certificate_is_expired(cert: ContestCertificate) -> bool:
    return cert.expires_at is not None and cert.expires_at < datetime.now(UTC)


@router.get("", response_model=list[ContestOut])
async def list_contests(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    # Bounded fetch + a page-aware cache key so a growing contest archive can't
    # turn this into an unbounded SELECT.
    cache_key = f"status={status_filter or ''}&limit={limit}&offset={offset}"
    cached = await cache_get_versioned("contests_list", cache_key)
    if cached is not None:
        return cached
    stmt = select(Contest).order_by(Contest.starts_at.desc()).limit(limit).offset(offset)
    if status_filter:
        stmt = stmt.where(Contest.status == status_filter)
    contests = (await db.execute(stmt)).scalars().all()
    out = [_contest_out(c) for c in contests]
    await cache_set_versioned("contests_list", cache_key, [o.model_dump(mode="json") for o in out], _CONTESTS_LIST_TTL)
    return out


@router.get("/upcoming", response_model=list[ContestOut])
async def upcoming_contests(db: AsyncSession = Depends(get_db)):
    cached = await cache_get_versioned("contests_list", "upcoming")
    if cached is not None:
        return cached
    now = datetime.now(UTC)
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


@router.post("/ai-weekly/register", response_model=AIWeeklyRegisterOut, status_code=201)
async def register_ai_weekly_exam(payload: AIWeeklyRegisterIn, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Step 1 of the AI Weekly Exam: register for a subject+topic during the
    Thursday-only registration window. Does not start the timed exam —
    that happens separately via POST /contests/{contest_id}/attempts once
    the exam's scheduled slot opens (see ai_exam_service.py)."""
    attempt = await register_for_ai_weekly_exam(db, user, payload.subject_id, payload.topic_id)
    contest = await db.get(Contest, attempt.contest_id)
    await bump_cache_version("contests_list")
    return AIWeeklyRegisterOut(
        attempt_id=attempt.id, contest_id=contest.id, contest_title=contest.title,
        starts_at=contest.starts_at, ends_at=contest.ends_at, status=attempt.status,
    )


@router.post("/{contest_id}/attempts", response_model=ContestAttemptStartOut, status_code=201)
async def start_contest_attempt(contest_id: uuid.UUID, request: Request, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    contest = await db.get(Contest, contest_id)
    if contest is None or contest.status != "open":
        raise NotFoundError("Contest not found or not currently open.")
    now = datetime.now(UTC)
    if now < contest.starts_at:
        raise ConflictError("This contest hasn't started yet.")
    if now > contest.ends_at:
        raise ConflictError("This contest window has closed.")

    client_ip = get_client_ip(request)
    existing = (await db.execute(select(ContestAttempt).where(ContestAttempt.contest_id == contest_id, ContestAttempt.student_id == user.id))).scalar_one_or_none()

    # The AI Weekly Exam requires having registered first (see
    # POST /contests/ai-weekly/register) — every other contest type has
    # always allowed a direct first start with no separate registration step.
    if contest.contest_type == "ai_weekly" and existing is None:
        raise ConflictError("You must register for this AI Weekly Exam before it opens.")

    if existing:
        if existing.status == "in_progress":
            if existing.allowed_ip and existing.allowed_ip != client_ip:
                raise ConflictError("This attempt is bound to a different network address.")
            remaining = (existing.server_deadline_at - now).total_seconds()
            return ContestAttemptStartOut(attempt_id=existing.id, server_deadline_at=existing.server_deadline_at, remaining_seconds=max(0, int(remaining)), resumed=True)
        if existing.status != "registered":
            raise ConflictError("You've already competed in this contest — one attempt per student.")
        # status == "registered": fall through and start the real timed window.

    question_ids = [uuid.UUID(q) for q in contest.question_ids]
    import random
    random.shuffle(question_ids)
    deadline = min(now + timedelta(seconds=contest.duration_seconds), contest.ends_at)
    if existing is not None:
        existing.question_order = [str(q) for q in question_ids]
        existing.server_deadline_at = deadline
        existing.allowed_ip = client_ip
        existing.status = "in_progress"
        existing.started_at = now
        attempt = existing
    else:
        attempt = ContestAttempt(
            contest_id=contest_id, student_id=user.id, question_order=[str(q) for q in question_ids],
            server_deadline_at=deadline, allowed_ip=client_ip,
        )
        db.add(attempt)
    await record_audit_event(db, actor_id=user.id, action="contest.attempt_started", resource_type="contest_attempt", metadata={"contest_type": contest.contest_type, "allowed_ip_bound": bool(client_ip)})
    await db.commit()
    await db.refresh(attempt)
    return ContestAttemptStartOut(attempt_id=attempt.id, server_deadline_at=deadline, remaining_seconds=int((deadline - now).total_seconds()), resumed=False)


async def _force_finalize_contest_attempt(db: AsyncSession, attempt: ContestAttempt, user: User, now: datetime) -> None:
    """Auto-submits a contest attempt that hit its integrity-violation limit
    — same shape as the grading loop in submit_contest_attempt, just
    triggered by exam_security rather than a student's own submit call."""
    rows = (await db.execute(select(ContestAnswer).where(ContestAnswer.attempt_id == attempt.id))).scalars().all()
    answered_qids = {row.question_id for row in rows}
    points_earned = sum(row.points_awarded for row in rows)
    points_possible = 0
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
            points_possible += question.points
            db.add(ContestAnswer(attempt_id=attempt.id, question_id=qid, selected_option_ids=[], is_correct=False, points_awarded=0))
    # Add back the points_possible already contributed by answered questions.
    answered_qids_list = list(answered_qids)
    if answered_qids_list:
        answered_questions = (await db.execute(select(Question).where(Question.id.in_(answered_qids_list)))).scalars().all()
        points_possible += sum(q.points for q in answered_questions)

    score_percent, _ = summarize_attempt(points_earned, points_possible, 0)
    attempt.points_earned = points_earned
    attempt.points_possible = points_possible
    attempt.score_percent = score_percent
    attempt.status = "submitted"
    attempt.submitted_at = now
    attempt.time_taken_seconds = int((now - attempt.started_at).total_seconds())
    attempt.flagged_events = attempt.flagged_events + [{"type": "auto_submit_integrity_limit", "at": now.isoformat()}]
    await record_audit_event(db, actor_id=user.id, action="contest.auto_submitted_integrity", resource_type="contest_attempt", resource_id=str(attempt.id), metadata={"violation_count": attempt.violation_count, "score_percent": score_percent})
    await cache_delete(_leaderboard_cache_key(attempt.contest_id))


@router.put("/attempts/{attempt_id}/events", response_model=dict)
async def contest_integrity_event(attempt_id: uuid.UUID, payload: IntegrityEventIn, request: Request, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    attempt = await db.get(ContestAttempt, attempt_id)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.allowed_ip and attempt.allowed_ip != get_client_ip(request):
        raise ConflictError("This attempt is bound to a different network address.")
    if attempt.status != "in_progress":
        return {"logged": False, "violation_count": attempt.violation_count, "auto_submitted": attempt.status == "submitted"}

    contest = await db.get(Contest, attempt.contest_id)
    if contest is None:
        raise NotFoundError("Contest not found.")

    attempt.violation_count = min(attempt.violation_count + 1, 1000)
    if len(attempt.flagged_events or []) < MAX_FLAGGED_EVENTS_PER_ATTEMPT:
        attempt.flagged_events = (attempt.flagged_events or []) + [{"type": payload.event_type, "at": datetime.now(UTC).isoformat()}]
    auto_submitted = False
    if contest.integrity_monitoring_enabled and attempt.violation_count >= contest.max_integrity_violations:
        await _force_finalize_contest_attempt(db, attempt, user, datetime.now(UTC))
        auto_submitted = True
    await db.commit()
    return {"logged": True, "violation_count": attempt.violation_count, "auto_submitted": auto_submitted}


@router.get("/{contest_id}/flagged-attempts", response_model=list[FlaggedAttemptOut])
async def list_flagged_contest_attempts(contest_id: uuid.UUID, admin: User = Depends(require_permission("contests.manage")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ContestAttempt, User.full_name)
        .join(User, User.id == ContestAttempt.student_id)
        .where(ContestAttempt.contest_id == contest_id, ContestAttempt.violation_count > 0)
        .order_by(ContestAttempt.violation_count.desc())
    )).all()
    return [
        FlaggedAttemptOut(attempt_id=a.id, student_id=a.student_id, student_name=name, status=a.status, score_percent=a.score_percent, flagged_events=a.flagged_events)
        for a, name in rows
    ]


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
    attempt = await db.get(ContestAttempt, attempt_id, with_for_update=True)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.status != "in_progress":
        return ContestResultOut.model_validate(attempt)
    now = datetime.now(UTC)
    late = now > attempt.server_deadline_at
    # Batch-fetch the questions rather than querying per answer inside the loop:
    # during a timed contest every submit lands in the same narrow window, so a
    # per-question round-trip multiplies DB load exactly when it is highest.
    answer_qids = {ans.question_id for ans in payload.answers}
    questions_by_id = {
        q.id: q for q in (await db.execute(
            select(Question).where(Question.id.in_(answer_qids)).options(selectinload(Question.options))
        )).scalars().all()
    } if answer_qids else {}

    points_earned, points_possible = 0, 0
    for ans in payload.answers:
        question = questions_by_id.get(ans.question_id)
        if question is None:
            continue
        sel = [] if late else [str(i) for i in ans.selected_option_ids]
        is_correct, points = grade_answer(question, sel, None if late else ans.text_answer)
        points_earned += points
        points_possible += question.points
        db.add(ContestAnswer(attempt_id=attempt.id, question_id=question.id, selected_option_ids=sel, text_answer=ans.text_answer, is_correct=is_correct, points_awarded=points))
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
    certs = (await db.execute(select(ContestCertificate).where(ContestCertificate.student_id == user.id).order_by(ContestCertificate.issued_at.desc()))).scalars().all()
    return [_contest_certificate_out(cert) for cert in certs]


@router.get("/certificates/verify/{certificate_number}", response_model=ContestCertificatePublicOut)
async def verify_contest_certificate(certificate_number: str, db: AsyncSession = Depends(get_db)):
    cert = (await db.execute(select(ContestCertificate).where(ContestCertificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None:
        return ContestCertificatePublicOut(valid=False, certificate_number=None, contest_id=uuid.UUID(int=0), contest_title="", rank=0, score_percent=0, issued_at=datetime.now(UTC), invalid_reason="not_found")
    if cert.revoked_at is not None:
        reason = "revoked"
    elif _contest_certificate_is_expired(cert):
        reason = "expired"
    else:
        reason = None
    student = await db.get(User, cert.student_id)
    return ContestCertificatePublicOut(
        valid=reason is None, certificate_number=cert.certificate_number, contest_id=cert.contest_id,
        contest_title=cert.contest_title, rank=cert.rank, score_percent=cert.score_percent,
        issued_at=cert.issued_at, expires_at=cert.expires_at, revoked=cert.revoked_at is not None,
        verify_url=verification_url(cert.certificate_number), student_full_name=student.full_name if student else None,
        invalid_reason=reason,
    )


@router.get("/certificates/{certificate_number}/qr")
async def contest_certificate_qr(certificate_number: str, db: AsyncSession = Depends(get_db)):
    cert = (await db.execute(select(ContestCertificate).where(ContestCertificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None:
        raise NotFoundError("Contest certificate not found.")
    return Response(content=generate_qr_png_bytes(cert.certificate_number), media_type="image/png")


@router.get("/certificates/{certificate_number}/pdf")
async def contest_certificate_pdf(certificate_number: str, db: AsyncSession = Depends(get_db)):
    cert = (await db.execute(select(ContestCertificate).where(ContestCertificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None or cert.revoked_at is not None or _contest_certificate_is_expired(cert):
        raise NotFoundError("Contest certificate not found.")
    student = await db.get(User, cert.student_id)
    try:
        pdf_bytes = generate_pdf_bytes(cert, student)
    except ImportError as exc:
        raise ServiceUnavailableError("PDF generation is temporarily unavailable on this server.") from exc
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{cert.certificate_number}.pdf"'})


@router.post("/certificates/{certificate_number}/revoke", response_model=ContestCertificateRevokeOut)
async def revoke_contest_certificate(
    certificate_number: str,
    admin: User = Depends(require_permission("certificates.manage")),
    db: AsyncSession = Depends(get_db),
):
    cert = (await db.execute(select(ContestCertificate).where(ContestCertificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None:
        raise NotFoundError("Contest certificate not found.")
    if cert.revoked_at is None:
        cert.revoked_at = datetime.now(UTC)
        await record_audit_event(db, actor_id=admin.id, action="contest_certificate.revoke", resource_type="contest_certificate", resource_id=str(cert.id))
        await db.commit()
    return ContestCertificateRevokeOut(certificate_number=cert.certificate_number, revoked_at=cert.revoked_at)


@router.post("/{contest_id}/finalize", response_model=ContestOut)
async def manual_finalize_contest(contest_id: uuid.UUID, user: User = Depends(require_permission("contests.manage")), db: AsyncSession = Depends(get_db)):
    contest = await db.get(Contest, contest_id)
    if contest is None:
        raise NotFoundError("Contest not found.")
    if datetime.now(UTC) < contest.ends_at:
        raise ConflictError("This contest's window hasn't closed yet.")
    contest = await finalize_contest(db, contest)
    return _contest_out(contest)
