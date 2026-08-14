from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_verified_user, require_permission
from app.models.assessment import Exam, ExamAnswer, ExamAttempt, Question
from app.models.user import User
from app.schemas.assessment import AnswerSubmit, AttemptResultOut, AttemptSubmit, ExamCreate, ExamOut, QuestionPublicOut
from app.services.analytics_service import track_event
from app.services.audit_service import record_audit_event
from app.services.gamification_service import POINTS_EXAM_PASS, award_points, evaluate_and_award_badges
from app.services.n8n_service import emit_event
from app.services.rate_limit_service import enforce_rate_limit
from app.services.scoring_service import grade_answer, summarize_attempt

router = APIRouter(prefix="/exams", tags=["exams"])


@router.post("", response_model=ExamOut, status_code=201)
async def create_exam(payload: ExamCreate, user: User = Depends(require_permission("exam.manage")), db: AsyncSession = Depends(get_db)):
    exam = Exam(
        course_id=payload.course_id, title=payload.title, time_limit_seconds=payload.time_limit_seconds,
        max_attempts=payload.max_attempts, pass_score_percent=payload.pass_score_percent,
        question_ids=[str(q) for q in payload.question_ids],
    )
    db.add(exam)
    await record_audit_event(db, actor_id=user.id, action="exam.create", resource_type="exam")
    await db.commit()
    await db.refresh(exam)
    return exam


@router.post("/{exam_id}/publish", response_model=ExamOut)
async def publish_exam(exam_id: uuid.UUID, user: User = Depends(require_permission("exam.manage")), db: AsyncSession = Depends(get_db)):
    exam = await db.get(Exam, exam_id)
    if exam is None:
        raise NotFoundError("Exam not found.")
    exam.is_published = True
    await record_audit_event(db, actor_id=user.id, action="exam.publish", resource_type="exam", resource_id=str(exam_id))
    await db.commit()
    await db.refresh(exam)
    return exam


@router.post("/{exam_id}/attempts", response_model=dict, status_code=201)
async def start_exam_attempt(exam_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"exam-start:{user.id}", limit=10, window_seconds=3600)

    exam = await db.get(Exam, exam_id)
    if exam is None or not exam.is_published:
        raise NotFoundError("Exam not found.")

    now = datetime.now(timezone.utc)
    if exam.available_from and now < exam.available_from:
        raise ConflictError("This exam is not open yet.")
    if exam.available_until and now > exam.available_until:
        raise ConflictError("This exam window has closed.")

    prior = (await db.execute(
        select(ExamAttempt).where(ExamAttempt.exam_id == exam_id, ExamAttempt.student_id == user.id)
    )).scalars().all()
    in_progress = next((a for a in prior if a.status == "in_progress"), None)
    if in_progress:
        remaining = (in_progress.server_deadline_at - now).total_seconds()
        return {
            "attempt_id": str(in_progress.id),
            "server_deadline_at": in_progress.server_deadline_at.isoformat(),
            "remaining_seconds": max(0, int(remaining)),
            "resumed": True,
        }
    if len(prior) >= exam.max_attempts:
        raise ConflictError("Maximum attempts reached for this exam.")

    question_ids = [uuid.UUID(q) for q in exam.question_ids]
    random.shuffle(question_ids)
    deadline = now + timedelta(seconds=exam.time_limit_seconds)

    attempt = ExamAttempt(
        exam_id=exam_id, student_id=user.id, attempt_number=len(prior) + 1,
        question_order=[str(q) for q in question_ids], server_deadline_at=deadline,
    )
    db.add(attempt)
    await record_audit_event(db, actor_id=user.id, action="exam.attempt_started", resource_type="exam_attempt")
    await db.commit()
    await db.refresh(attempt)

    return {"attempt_id": str(attempt.id), "server_deadline_at": deadline.isoformat(),
            "remaining_seconds": exam.time_limit_seconds, "resumed": False}


@router.get("/attempts/{attempt_id}/questions", response_model=list[QuestionPublicOut])
async def get_attempt_questions(attempt_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    attempt = await db.get(ExamAttempt, attempt_id)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    question_ids = [uuid.UUID(q) for q in attempt.question_order]
    result = await db.execute(select(Question).where(Question.id.in_(question_ids)).options(selectinload(Question.options)))
    questions = {q.id: q for q in result.scalars().all()}
    return [QuestionPublicOut.model_validate(questions[q]) for q in question_ids if q in questions]


@router.put("/attempts/{attempt_id}/autosave", response_model=dict)
async def autosave_answer(attempt_id: uuid.UUID, payload: AnswerSubmit, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Persists a single answer immediately so a dropped connection never loses
    work (spec section 15: autosave, recovery after network failure)."""
    attempt = await db.get(ExamAttempt, attempt_id)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.status != "in_progress":
        raise ConflictError("This attempt is no longer active.")
    if datetime.now(timezone.utc) > attempt.server_deadline_at:
        raise ConflictError("Time is up for this attempt. Submit to finalize.")

    existing = (await db.execute(
        select(ExamAnswer).where(ExamAnswer.attempt_id == attempt_id, ExamAnswer.question_id == payload.question_id)
    )).scalar_one_or_none()
    if existing is None:
        existing = ExamAnswer(attempt_id=attempt_id, question_id=payload.question_id)
        db.add(existing)
    existing.selected_option_ids = [str(i) for i in payload.selected_option_ids]
    existing.text_answer = payload.text_answer
    existing.autosaved_at = datetime.now(timezone.utc)
    attempt.autosaved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"saved": True, "autosaved_at": existing.autosaved_at.isoformat()}


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptResultOut)
async def submit_exam_attempt(attempt_id: uuid.UUID, payload: AttemptSubmit, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    # See the matching comment in quizzes.py::submit_attempt — with_for_update
    # closes the race where two concurrent submits for the same attempt both
    # observe status == "in_progress" and both grade/award points before
    # either commits. The submission_client_token check below still matters
    # for its own case (a client-side retry that reuses the same token), but
    # it doesn't protect against two genuinely different concurrent requests
    # without this lock.
    attempt = await db.get(ExamAttempt, attempt_id, with_for_update=True)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")

    # Idempotency: a duplicate submit (double-click, retry after timeout) with the same
    # client_token — or any submit once already submitted — returns the existing result
    # rather than re-grading (spec section 15: "anti-duplicate submissions").
    if attempt.status != "in_progress":
        return attempt
    if payload.client_token and attempt.submission_client_token == payload.client_token:
        return attempt

    exam = await db.get(Exam, attempt.exam_id)
    now = datetime.now(timezone.utc)
    late = now > attempt.server_deadline_at

    # Merge autosaved answers with whatever came in the final submit payload —
    # final payload wins per-question, autosave fills any gaps.
    autosaved = {a.question_id: a for a in (await db.execute(
        select(ExamAnswer).where(ExamAnswer.attempt_id == attempt_id)
    )).scalars().all()}
    submitted_by_qid = {a.question_id: a for a in payload.answers}

    points_earned, points_possible = 0, 0
    for qid in set(autosaved) | set(submitted_by_qid):
        question = (await db.execute(
            select(Question).where(Question.id == qid).options(selectinload(Question.options))
        )).scalar_one_or_none()
        if question is None:
            continue
        if qid in submitted_by_qid and not late:
            sel = [str(i) for i in submitted_by_qid[qid].selected_option_ids]
            text = submitted_by_qid[qid].text_answer
        elif qid in autosaved:
            sel = autosaved[qid].selected_option_ids
            text = autosaved[qid].text_answer
        else:
            sel, text = [], None

        is_correct, points = grade_answer(question, sel, text)
        points_earned += points
        points_possible += question.points

        row = autosaved.get(qid)
        if row is None:
            row = ExamAnswer(attempt_id=attempt.id, question_id=qid)
            db.add(row)
        row.selected_option_ids = sel
        row.text_answer = text
        row.is_correct = is_correct
        row.points_awarded = points

    score_percent, passed = summarize_attempt(points_earned, points_possible, exam.pass_score_percent)
    attempt.points_earned = points_earned
    attempt.points_possible = points_possible
    attempt.score_percent = score_percent
    attempt.passed = passed
    attempt.status = "submitted"
    attempt.submitted_at = now
    attempt.submission_client_token = payload.client_token
    if late:
        attempt.flagged_events = attempt.flagged_events + [{"type": "late_submission", "at": now.isoformat()}]

    if passed:
        await award_points(db, user.id, POINTS_EXAM_PASS, reason="exam_pass", reference_id=exam.id)
        await evaluate_and_award_badges(db, user.id, "exam_pass", {"score_percent": score_percent})

    await record_audit_event(db, actor_id=user.id, action="exam.attempt_submitted", resource_type="exam_attempt",
                              resource_id=str(attempt.id), metadata={"score_percent": score_percent, "passed": passed})
    await track_event(db, event_type="exam_completed", user_id=user.id,
                       metadata={"exam_id": str(exam.id), "score_percent": score_percent, "passed": passed})
    await db.commit()
    await db.refresh(attempt)
    await emit_event("exam.completed", {
        "email": user.email, "assessment_title": exam.title, "score_percent": score_percent, "passed": passed,
    })
    return attempt
