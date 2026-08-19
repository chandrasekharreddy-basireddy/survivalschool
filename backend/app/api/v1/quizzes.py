from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_verified_user, require_course_ownership, require_permission
from app.models.assessment import Question, QuestionOption, Quiz, QuizAnswer, QuizAttempt
from app.models.user import User
from app.schemas.assessment import (
    AttemptHistoryOut,
    AttemptResultOut,
    AttemptSubmit,
    QuestionCreate,
    QuestionOut,
    QuestionPublicOut,
    QuizCreate,
    QuizOut,
)
from app.schemas.question_import import ImportPreviewOut, ImportRowOut
from app.services.analytics_service import track_event
from app.services.audit_service import record_audit_event
from app.services.gamification_service import (
    POINTS_QUIZ_PASS,
    award_points,
    evaluate_and_award_badges,
)
from app.services.n8n_service import emit_event
from app.services.question_import_service import commit_rows, parse_csv, parse_xlsx
from app.services.scoring_service import grade_answer, summarize_attempt

router = APIRouter(prefix="/quizzes", tags=["quizzes"])
questions_router = APIRouter(prefix="/questions", tags=["question-bank"])


@questions_router.post("", response_model=QuestionOut, status_code=201)
async def create_question(
    payload: QuestionCreate,
    user: User = Depends(require_permission("quiz.create", "exam.manage")),
    db: AsyncSession = Depends(get_db),
):
    # quiz.create/exam.manage are granted to every INSTRUCTOR — without this,
    # any instructor could add questions to any other instructor's course.
    await require_course_ownership(db, user, payload.course_id)
    if payload.question_type in ("single", "true_false") and sum(1 for o in payload.options if o.is_correct) != 1:
        raise ValidationAppError("single/true_false questions must have exactly one correct option.")
    if payload.question_type == "multiple" and sum(1 for o in payload.options if o.is_correct) < 1:
        raise ValidationAppError("multiple-answer questions need at least one correct option.")

    question = Question(
        course_id=payload.course_id, prompt=payload.prompt, question_type=payload.question_type,
        points=payload.points, explanation=payload.explanation, short_answer_key=payload.short_answer_key,
    )
    db.add(question)
    await db.flush()
    for opt in payload.options:
        db.add(QuestionOption(question_id=question.id, text=opt.text, is_correct=opt.is_correct, order_index=opt.order_index))
    await record_audit_event(db, actor_id=user.id, action="question.create", resource_type="question", resource_id=str(question.id))
    await db.commit()
    return question


@questions_router.post("/bulk-import", response_model=ImportPreviewOut)
async def bulk_import_questions(
    course_id: uuid.UUID,
    dry_run: bool = Query(True, description="Preview only (default). Pass dry_run=false to actually commit, and only once every row is error-free."),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("quiz.create", "exam.manage")),
    db: AsyncSession = Depends(get_db),
):
    """CSV or XLSX bulk question import — see app/services/question_import_service.py
    for the expected column format. All-or-nothing: a commit (dry_run=false)
    only writes anything if every row in the file is valid; otherwise nothing
    is inserted and the same per-row errors are returned so the instructor
    can fix the file and re-upload."""
    await require_course_ownership(db, user, course_id)

    raw = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".xlsx"):
        rows = parse_xlsx(raw)
    elif filename.endswith(".csv"):
        rows = parse_csv(raw)
    else:
        raise ValidationAppError("Only .csv or .xlsx files are supported.")

    error_rows = [r for r in rows if r.error]
    inserted_count = 0
    committed = False
    if not dry_run and not error_rows and rows:
        inserted_count = await commit_rows(db, course_id, rows)
        committed = True
        await record_audit_event(db, actor_id=user.id, action="question.bulk_import", resource_type="course",
                                  resource_id=str(course_id), metadata={"inserted_count": inserted_count})

    return ImportPreviewOut(
        total_rows=len(rows), valid_rows=len(rows) - len(error_rows), error_rows=len(error_rows),
        rows=[ImportRowOut(row_number=r.row_number, prompt=r.prompt, question_type=r.question_type, error=r.error) for r in rows],
        committed=committed, inserted_count=inserted_count,
    )


@router.post("", response_model=QuizOut, status_code=201)
async def create_quiz(
    payload: QuizCreate,
    user: User = Depends(require_permission("quiz.manage")),
    db: AsyncSession = Depends(get_db),
):
    # quiz.manage is granted to every INSTRUCTOR — without this, any
    # instructor could create a quiz under any other instructor's course.
    await require_course_ownership(db, user, payload.course_id)
    quiz = Quiz(
        course_id=payload.course_id, title=payload.title, time_limit_seconds=payload.time_limit_seconds,
        max_attempts=payload.max_attempts, randomize_questions=payload.randomize_questions,
        pass_score_percent=payload.pass_score_percent, question_ids=[str(q) for q in payload.question_ids],
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)
    return quiz


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(quiz_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise NotFoundError("Quiz not found.")
    return quiz


@router.post("/{quiz_id}/publish", response_model=QuizOut)
async def publish_quiz(quiz_id: uuid.UUID, user: User = Depends(require_permission("quiz.manage")), db: AsyncSession = Depends(get_db)):
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise NotFoundError("Quiz not found.")
    await require_course_ownership(db, user, quiz.course_id)
    quiz.is_published = True
    await db.commit()
    await db.refresh(quiz)
    return quiz


@router.post("/{quiz_id}/attempts", response_model=list[QuestionPublicOut], status_code=201)
async def start_attempt(quiz_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None or not quiz.is_published:
        raise NotFoundError("Quiz not found.")

    prior_count = (await db.execute(
        select(QuizAttempt).where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.student_id == user.id)
    )).scalars().all()
    if len(prior_count) >= quiz.max_attempts:
        raise ConflictError("Maximum attempts reached for this quiz.")

    question_ids = [uuid.UUID(q) for q in quiz.question_ids]
    if quiz.randomize_questions:
        random.shuffle(question_ids)

    attempt = QuizAttempt(quiz_id=quiz_id, student_id=user.id, attempt_number=len(prior_count) + 1,
                           question_order=[str(q) for q in question_ids])
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    result = await db.execute(
        select(Question).where(Question.id.in_(question_ids)).options(selectinload(Question.options))
    )
    questions = {q.id: q for q in result.scalars().all()}
    ordered = [questions[qid] for qid in question_ids if qid in questions]
    # attach attempt id via header-like trick: return via a wrapper would be cleaner,
    # but to keep the response a flat list matching QuestionPublicOut we expose attempt id
    # through a dedicated endpoint below instead.
    return [QuestionPublicOut.model_validate(q) for q in ordered]


@router.get("/me/attempts", response_model=list[AttemptHistoryOut])
async def my_quiz_attempts(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = (await db.execute(
        select(QuizAttempt, Quiz.title)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(QuizAttempt.student_id == user.id)
        .order_by(QuizAttempt.started_at.desc())
        .limit(limit).offset(offset)
    )).all()
    return [
        AttemptHistoryOut(
            id=a.id, quiz_id=a.quiz_id, title=title, attempt_number=a.attempt_number,
            status=a.status, score_percent=a.score_percent, passed=a.passed,
            started_at=a.started_at, submitted_at=a.submitted_at,
        )
        for a, title in rows
    ]


@router.get("/{quiz_id}/attempts/current", response_model=dict)
async def current_attempt(quiz_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    attempt = (await db.execute(
        select(QuizAttempt).where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.student_id == user.id, QuizAttempt.status == "in_progress")
        .order_by(QuizAttempt.attempt_number.desc())
    )).scalars().first()
    if attempt is None:
        raise NotFoundError("No in-progress attempt. Start one first.")
    return {"attempt_id": str(attempt.id), "started_at": attempt.started_at.isoformat()}


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptResultOut)
async def submit_attempt(attempt_id: uuid.UUID, payload: AttemptSubmit, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    # with_for_update takes a row lock on this attempt for the rest of the
    # transaction. Without it, two concurrent submits (double-click, a client
    # retry racing the original request, two open tabs) can both read
    # status == "in_progress" before either commits, both grade, and both
    # award points/badges — the idempotency check below only closes that gap
    # if reads are serialized against each other, which requires the lock.
    # A second request now simply blocks here until the first one commits,
    # then re-reads with status == "submitted" and takes the early return.
    attempt = await db.get(QuizAttempt, attempt_id, with_for_update=True)
    if attempt is None or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.status != "in_progress":
        # idempotent: re-posting a submitted attempt just returns the stored result,
        # never re-grades or double-awards points (spec: "anti-duplicate submissions").
        return attempt

    quiz = await db.get(Quiz, attempt.quiz_id)
    points_earned, points_possible = 0, 0

    # Batch-fetch instead of one query per answer — a 50-question quiz
    # submitted by a full cohort at once was doing 50 sequential DB round
    # trips on the hot submission path (same fix already applied to the
    # exam/contest submit endpoints).
    answer_qids = {ans.question_id for ans in payload.answers}
    questions_by_id = {
        q.id: q for q in (await db.execute(
            select(Question).where(Question.id.in_(answer_qids)).options(selectinload(Question.options))
        )).scalars().all()
    } if answer_qids else {}

    for ans in payload.answers:
        question = questions_by_id.get(ans.question_id)
        if question is None:
            continue
        is_correct, points = grade_answer(question, [str(i) for i in ans.selected_option_ids], ans.text_answer)
        points_earned += points
        points_possible += question.points
        db.add(QuizAnswer(
            attempt_id=attempt.id, question_id=question.id,
            selected_option_ids=[str(i) for i in ans.selected_option_ids],
            text_answer=ans.text_answer, is_correct=is_correct, points_awarded=points,
        ))

    score_percent, passed = summarize_attempt(points_earned, points_possible, quiz.pass_score_percent)
    attempt.points_earned = points_earned
    attempt.points_possible = points_possible
    attempt.score_percent = score_percent
    attempt.passed = passed
    attempt.status = "submitted"
    attempt.submitted_at = datetime.now(UTC)

    if passed:
        await award_points(db, user.id, POINTS_QUIZ_PASS, reason="quiz_pass", reference_id=quiz.id)
        await evaluate_and_award_badges(db, user.id, "quiz_pass", {"score_percent": score_percent})

    await track_event(db, event_type="quiz_completed", user_id=user.id,
                       metadata={"quiz_id": str(quiz.id), "score_percent": score_percent, "passed": passed})
    await db.commit()
    await db.refresh(attempt)
    await emit_event("quiz.completed", {
        "email": user.email, "assessment_title": quiz.title, "score_percent": score_percent, "passed": passed,
    })
    return attempt
