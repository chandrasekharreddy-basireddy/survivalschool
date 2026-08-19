from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_verified_user, require_course_ownership, require_permission
from app.models.assessment import Exam, ExamAnswer, ExamAttempt, Question
from app.models.lms import Course
from app.models.user import User
from app.schemas.assessment import (
    AnswerSubmit,
    AttemptHistoryOut,
    AttemptResultOut,
    AttemptReviewOut,
    AttemptSubmit,
    ExamCreate,
    ExamOut,
    FlaggedAttemptOut,
    QuestionPublicOut,
    ReviewAnswerOut,
)
from app.services.analytics_service import track_event
from app.services.audit_service import record_audit_event
from app.services.gamification_service import POINTS_EXAM_PASS, award_points, evaluate_and_award_badges
from app.services.n8n_service import emit_event
from app.services.scoring_service import grade_answer, summarize_attempt

router = APIRouter(prefix="/exams", tags=["exams"])


@router.post("", response_model=ExamOut, status_code=201)
async def create_exam(payload: ExamCreate, user: User = Depends(require_permission("exam.manage")), db: AsyncSession = Depends(get_db)):
    # exam.manage is granted to every INSTRUCTOR — without this, any instructor
    # could create an exam under any other instructor's course.
    await require_course_ownership(db, user, payload.course_id)
    exam = Exam(
        course_id=payload.course_id, title=payload.title, time_limit_seconds=payload.time_limit_seconds,
        max_attempts=payload.max_attempts, pass_score_percent=payload.pass_score_percent,
        question_ids=[str(q) for q in payload.question_ids],
        fullscreen_required=payload.fullscreen_required, integrity_monitoring_enabled=payload.integrity_monitoring_enabled,
    )
    db.add(exam)
    await record_audit_event(db, actor_id=user.id, action="exam.create", resource_type="exam")
    await db.commit()
    await db.refresh(exam)
    return exam


@router.get("/{exam_id}", response_model=ExamOut)
async def get_exam(
    exam_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    # Requires authentication: exam metadata (title, timing, and especially the
    # question_ids list) is sensitive pre-exam information, and this endpoint
    # used to be fully anonymous — anyone who guessed a UUID could read it.
    # Unpublished exams stay visible only to users who can manage exams.
    exam = await db.get(Exam, exam_id)
    if exam is None:
        raise NotFoundError("Exam not found.")
    if not exam.is_published and not user.has_permission("exam.manage"):
        raise NotFoundError("Exam not found.")
    return exam


@router.post("/{exam_id}/publish", response_model=ExamOut)
async def publish_exam(exam_id: uuid.UUID, user: User = Depends(require_permission("exam.manage")), db: AsyncSession = Depends(get_db)):
    exam = await db.get(Exam, exam_id)
    if exam is None:
        raise NotFoundError("Exam not found.")
    await require_course_ownership(db, user, exam.course_id)
    exam.is_published = True
    await record_audit_event(db, actor_id=user.id, action="exam.publish", resource_type="exam", resource_id=str(exam_id))
    await db.commit()
    await db.refresh(exam)
    return exam


# POST /{exam_id}/attempts lives in exam_security.py (secure_start_exam_attempt)
# — it adds IP-binding on top of the same logic and is registered first, so
# this router's copy used to be silent dead code. Deleted rather than kept in
# sync by hand; see router.py's include_router order.


@router.get("/me/attempts", response_model=list[AttemptHistoryOut])
async def my_exam_attempts(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # Paginated: a prolific student can accumulate thousands of attempts, and an
    # unbounded SELECT loads them all into memory on every dashboard load.
    rows = (await db.execute(
        select(ExamAttempt, Exam.title)
        .join(Exam, Exam.id == ExamAttempt.exam_id)
        .where(ExamAttempt.student_id == user.id)
        .order_by(ExamAttempt.started_at.desc())
        .limit(limit).offset(offset)
    )).all()
    return [
        AttemptHistoryOut(
            id=a.id, exam_id=a.exam_id, title=title, attempt_number=a.attempt_number,
            status=a.status, score_percent=a.score_percent, passed=a.passed,
            started_at=a.started_at, submitted_at=a.submitted_at,
        )
        for a, title in rows
    ]


@router.get("/attempts/{attempt_id}/review", response_model=AttemptReviewOut)
async def review_exam_attempt(attempt_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Post-submission review: shows the student what they answered vs. the
    correct options. Deliberately requires status == 'submitted' — an
    in-progress attempt never exposes correct answers (that would let a
    student reload the review endpoint mid-exam to cheat)."""
    attempt = await db.get(ExamAttempt, attempt_id)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.status != "submitted":
        raise ConflictError("This attempt hasn't been submitted yet.")

    answer_rows = (await db.execute(
        select(ExamAnswer).where(ExamAnswer.attempt_id == attempt_id)
    )).scalars().all()
    answers_by_qid = {a.question_id: a for a in answer_rows}

    question_ids = [uuid.UUID(q) for q in attempt.question_order]
    questions = (await db.execute(
        select(Question).where(Question.id.in_(question_ids)).options(selectinload(Question.options))
    )).scalars().all()
    questions_by_id = {q.id: q for q in questions}

    review_answers = []
    for qid in question_ids:
        question = questions_by_id.get(qid)
        if question is None:
            continue
        ans = answers_by_qid.get(qid)
        correct_ids = [o.id for o in question.options if o.is_correct]
        review_answers.append(ReviewAnswerOut(
            question_id=qid, prompt=question.prompt, question_type=question.question_type,
            selected_option_ids=[uuid.UUID(i) for i in (ans.selected_option_ids if ans else [])],
            correct_option_ids=correct_ids,
            is_correct=ans.is_correct if ans else None,
            points_awarded=ans.points_awarded if ans else 0,
            points_possible=question.points,
            explanation=question.explanation,
        ))

    return AttemptReviewOut(
        attempt_id=attempt.id, status=attempt.status, score_percent=attempt.score_percent,
        passed=attempt.passed, answers=review_answers,
    )


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

    # Batch-fetch every question before grading. Issuing the SELECT inside the
    # loop costs one DB round-trip per question, so a 50-question exam becomes
    # 50 sequential queries on the hot submit path — latency spikes and
    # connection-pool exhaustion when a cohort submits at the same time.
    all_qids = set(autosaved) | set(submitted_by_qid)
    questions_by_id = {
        q.id: q for q in (await db.execute(
            select(Question).where(Question.id.in_(all_qids)).options(selectinload(Question.options))
        )).scalars().all()
    } if all_qids else {}

    points_earned, points_possible = 0, 0
    for qid in all_qids:
        question = questions_by_id.get(qid)
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


# PUT /attempts/{attempt_id}/events lives in exam_security.py
# (secure_integrity_event) — same event-bound (MAX_FLAGGED_EVENTS_PER_ATTEMPT)
# now lives there too, plus IP-binding and auto-finalize-on-violation-limit
# that this copy never had. Deleted for the same reason as start_exam_attempt
# above: registered second, so this was silent dead code.


@router.get("/{exam_id}/attempts/flagged", response_model=list[FlaggedAttemptOut])
async def list_flagged_attempts(exam_id: uuid.UUID, user: User = Depends(require_permission("exam.manage")), db: AsyncSession = Depends(get_db)):
    """Instructor-facing: every submitted attempt on this exam that has at
    least one flagged integrity event, for manual review. Scoped to the
    exam's own course instructor (or an admin) — one instructor can never
    see another instructor's exam integrity data."""
    exam = await db.get(Exam, exam_id)
    if exam is None:
        raise NotFoundError("Exam not found.")
    course = await db.get(Course, exam.course_id)
    if course is None or (course.instructor_id != user.id and not user.has_permission("system.manage")):
        raise AuthorizationError("You can only review integrity flags for your own exams.")

    from sqlalchemy import func
    rows = (await db.execute(
        select(ExamAttempt, User.full_name)
        .join(User, User.id == ExamAttempt.student_id)
        .where(ExamAttempt.exam_id == exam_id, func.json_array_length(ExamAttempt.flagged_events) > 0)
    )).all()
    return [
        FlaggedAttemptOut(attempt_id=a.id, student_id=a.student_id, student_name=name, status=a.status,
                           score_percent=a.score_percent, flagged_events=a.flagged_events)
        for a, name in rows
    ]
