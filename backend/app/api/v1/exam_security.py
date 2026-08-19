from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import get_client_ip, get_current_verified_user
from app.models.assessment import Exam, ExamAnswer, ExamAttempt, Question
from app.models.user import User
from app.schemas.assessment import IntegrityEventIn
from app.services.analytics_service import track_event
from app.services.audit_service import record_audit_event
from app.services.gamification_service import POINTS_EXAM_PASS, award_points, evaluate_and_award_badges
from app.services.rate_limit_service import enforce_rate_limit
from app.services.scoring_service import grade_answer, summarize_attempt

router = APIRouter(prefix="/exams", tags=["exam-security"])

# Bounds flagged_events growth — a spammy or buggy client calling this
# endpoint repeatedly can't grow an attempt's event log without limit.
MAX_FLAGGED_EVENTS_PER_ATTEMPT = 200


async def _force_finalize_attempt(db: AsyncSession, attempt: ExamAttempt, user: User, exam: Exam, now: datetime) -> None:
    rows = (await db.execute(select(ExamAnswer).where(ExamAnswer.attempt_id == attempt.id))).scalars().all()
    answers = {row.question_id: row for row in rows}
    points_earned = 0
    points_possible = 0

    for qid_text in attempt.question_order:
        qid = uuid.UUID(qid_text)
        question = (await db.execute(select(Question).where(Question.id == qid).options(selectinload(Question.options)))).scalar_one_or_none()
        if question is None:
            continue
        points_possible += question.points
        row = answers.get(qid)
        selected = row.selected_option_ids if row else []
        text_answer = row.text_answer if row else None
        is_correct, points = grade_answer(question, selected, text_answer)
        points_earned += points
        if row:
            row.is_correct = is_correct
            row.points_awarded = points

    score, passed = summarize_attempt(points_earned, points_possible, exam.pass_score_percent)
    attempt.points_earned = points_earned
    attempt.points_possible = points_possible
    attempt.score_percent = score
    attempt.passed = passed
    attempt.status = "submitted"
    attempt.submitted_at = now
    attempt.flagged_events = attempt.flagged_events + [{"type": "auto_submit_integrity_limit", "at": now.isoformat()}]
    if passed:
        await award_points(db, user.id, POINTS_EXAM_PASS, reason="exam_pass", reference_id=exam.id)
        await evaluate_and_award_badges(db, user.id, "exam_pass", {"score_percent": score})
    await record_audit_event(db, actor_id=user.id, action="exam.auto_submitted_integrity", resource_type="exam_attempt", resource_id=str(attempt.id), metadata={"violation_count": attempt.violation_count, "score_percent": score})
    await track_event(db, event_type="exam_completed", user_id=user.id, metadata={"exam_id": str(exam.id), "score_percent": score, "passed": passed, "auto_submitted": True})


@router.post("/{exam_id}/attempts", response_model=dict, status_code=201)
async def secure_start_exam_attempt(exam_id: uuid.UUID, request: Request, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"exam-start:{user.id}", limit=10, window_seconds=3600)
    exam = await db.get(Exam, exam_id)
    if exam is None or not exam.is_published:
        raise NotFoundError("Exam not found.")

    now = datetime.now(timezone.utc)
    if exam.available_from and now < exam.available_from:
        raise ConflictError("This exam is not open yet.")
    if exam.available_until and now > exam.available_until:
        raise ConflictError("This exam window has closed.")

    prior = (await db.execute(select(ExamAttempt).where(ExamAttempt.exam_id == exam_id, ExamAttempt.student_id == user.id))).scalars().all()
    in_progress = next((a for a in prior if a.status == "in_progress"), None)
    client_ip = get_client_ip(request)
    if in_progress:
        if in_progress.allowed_ip and in_progress.allowed_ip != client_ip:
            raise ConflictError("This exam attempt is bound to a different network address.")
        remaining = (in_progress.server_deadline_at - now).total_seconds()
        return {"attempt_id": str(in_progress.id), "server_deadline_at": in_progress.server_deadline_at.isoformat(), "remaining_seconds": max(0, int(remaining)), "resumed": True}
    if len(prior) >= exam.max_attempts:
        raise ConflictError("Maximum attempts reached for this exam.")

    question_ids = [uuid.UUID(q) for q in exam.question_ids]
    random.shuffle(question_ids)
    deadline = now + timedelta(seconds=exam.time_limit_seconds)
    attempt = ExamAttempt(exam_id=exam_id, student_id=user.id, attempt_number=len(prior) + 1, question_order=[str(q) for q in question_ids], server_deadline_at=deadline, allowed_ip=client_ip)
    db.add(attempt)
    await record_audit_event(db, actor_id=user.id, action="exam.attempt_started", resource_type="exam_attempt", metadata={"allowed_ip_bound": bool(client_ip)})
    await db.commit()
    await db.refresh(attempt)
    return {"attempt_id": str(attempt.id), "server_deadline_at": deadline.isoformat(), "remaining_seconds": exam.time_limit_seconds, "resumed": False}


@router.put("/attempts/{attempt_id}/events", response_model=dict)
async def secure_integrity_event(attempt_id: uuid.UUID, payload: IntegrityEventIn, request: Request, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    attempt = await db.get(ExamAttempt, attempt_id)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.allowed_ip and attempt.allowed_ip != get_client_ip(request):
        raise ConflictError("This exam attempt is bound to a different network address.")
    if attempt.status != "in_progress":
        return {"logged": False, "violation_count": attempt.violation_count, "auto_submitted": attempt.status == "submitted"}

    exam = await db.get(Exam, attempt.exam_id)
    if exam is None:
        raise NotFoundError("Exam not found.")

    attempt.violation_count = min(attempt.violation_count + 1, 1000)
    if len(attempt.flagged_events or []) < MAX_FLAGGED_EVENTS_PER_ATTEMPT:
        attempt.flagged_events = (attempt.flagged_events or []) + [{"type": payload.event_type, "at": datetime.now(timezone.utc).isoformat()}]
    auto_submitted = False
    if exam.integrity_monitoring_enabled and attempt.violation_count >= exam.max_integrity_violations:
        await _force_finalize_attempt(db, attempt, user, exam, datetime.now(timezone.utc))
        auto_submitted = True
    await db.commit()
    return {"logged": True, "violation_count": attempt.violation_count, "auto_submitted": auto_submitted}
