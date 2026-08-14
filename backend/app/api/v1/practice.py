from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_verified_user
from app.models.assessment import Exam, ExamAnswer, ExamAttempt, Question, Quiz, QuizAnswer, QuizAttempt
from app.models.lms import Course
from app.models.practice import PracticeAnswer, PracticeSession, QuestionBookmark
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.practice import (
    BookmarkCreate,
    BookmarkOut,
    PracticeAnswerResultOut,
    PracticeQuestionOut,
    PracticeResultOut,
    PracticeSessionHistoryOut,
    PracticeSessionStartOut,
    PracticeStartRequest,
    PracticeSubmit,
)
from app.services.scoring_service import grade_answer, summarize_attempt

router = APIRouter(tags=["practice"])


@router.post("/questions/{question_id}/bookmark", response_model=BookmarkOut, status_code=201)
async def bookmark_question(
    question_id: uuid.UUID,
    payload: BookmarkCreate,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    question = await db.get(Question, question_id)
    if question is None:
        raise NotFoundError("Question not found.")

    existing = (await db.execute(
        select(QuestionBookmark).where(QuestionBookmark.student_id == user.id, QuestionBookmark.question_id == question_id)
    )).scalar_one_or_none()
    if existing is None:
        try:
            async with db.begin_nested():
                existing = QuestionBookmark(student_id=user.id, question_id=question_id, note=payload.note)
                db.add(existing)
                await db.flush()
        except IntegrityError:
            existing = (await db.execute(
                select(QuestionBookmark).where(QuestionBookmark.student_id == user.id, QuestionBookmark.question_id == question_id)
            )).scalar_one()
    else:
        existing.note = payload.note
    await db.commit()
    await db.refresh(existing)

    course = await db.get(Course, question.course_id) if question.course_id else None
    return BookmarkOut(id=existing.id, question_id=question_id, prompt=question.prompt, question_type=question.question_type,
                        course_id=question.course_id, course_title=course.title if course else None,
                        note=existing.note, created_at=existing.created_at)


@router.delete("/questions/{question_id}/bookmark", response_model=MessageResponse)
async def remove_bookmark(
    question_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(QuestionBookmark).where(QuestionBookmark.student_id == user.id, QuestionBookmark.question_id == question_id)
    )).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()
    return MessageResponse(message="Bookmark removed.")


@router.get("/practice/bookmarks", response_model=list[BookmarkOut])
async def list_bookmarks(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(QuestionBookmark).where(QuestionBookmark.student_id == user.id).order_by(QuestionBookmark.created_at.desc())
    )).scalars().all()
    out = []
    for b in rows:
        question = await db.get(Question, b.question_id)
        if question is None:
            continue
        course = await db.get(Course, question.course_id) if question.course_id else None
        out.append(BookmarkOut(id=b.id, question_id=b.question_id, prompt=question.prompt, question_type=question.question_type,
                                course_id=question.course_id, course_title=course.title if course else None,
                                note=b.note, created_at=b.created_at))
    return out


async def _mistake_question_ids(db: AsyncSession, student_id: uuid.UUID, course_id: uuid.UUID | None) -> list[uuid.UUID]:
    """Every question this student has ever answered incorrectly on a
    submitted quiz or exam attempt, deduplicated, most-recent first."""
    quiz_stmt = (
        select(QuizAnswer.question_id, QuizAnswer.created_at)
        .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
        .where(QuizAttempt.student_id == student_id, QuizAnswer.is_correct.is_(False))
    )
    exam_stmt = (
        select(ExamAnswer.question_id, ExamAnswer.created_at)
        .join(ExamAttempt, ExamAttempt.id == ExamAnswer.attempt_id)
        .where(ExamAttempt.student_id == student_id, ExamAnswer.is_correct.is_(False))
    )
    if course_id is not None:
        quiz_stmt = quiz_stmt.join(Quiz, Quiz.id == QuizAttempt.quiz_id).where(Quiz.course_id == course_id)
        exam_stmt = exam_stmt.join(Exam, Exam.id == ExamAttempt.exam_id).where(Exam.course_id == course_id)

    quiz_rows = (await db.execute(quiz_stmt)).all()
    exam_rows = (await db.execute(exam_stmt)).all()
    by_id: dict[uuid.UUID, datetime] = {}
    for qid, created_at in [*quiz_rows, *exam_rows]:
        if qid not in by_id or created_at > by_id[qid]:
            by_id[qid] = created_at
    return [qid for qid, _ in sorted(by_id.items(), key=lambda kv: kv[1], reverse=True)]


@router.post("/practice/sessions", response_model=PracticeSessionStartOut, status_code=201)
async def start_practice_session(
    payload: PracticeStartRequest,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.source == "bookmarks":
        stmt = select(QuestionBookmark.question_id).where(QuestionBookmark.student_id == user.id)
        if payload.course_id:
            stmt = stmt.join(Question, Question.id == QuestionBookmark.question_id).where(Question.course_id == payload.course_id)
        question_ids = list((await db.execute(stmt)).scalars().all())
    elif payload.source == "mistakes":
        question_ids = await _mistake_question_ids(db, user.id, payload.course_id)
    elif payload.source == "course":
        if payload.course_id is None:
            raise ValidationAppError("course_id is required when source is 'course'.")
        question_ids = list((await db.execute(
            select(Question.id).where(Question.course_id == payload.course_id)
        )).scalars().all())
    else:
        raise ValidationAppError("Unknown practice source.")

    if not question_ids:
        raise NotFoundError(
            "Nothing to practice yet — "
            + {"bookmarks": "bookmark a question first.", "mistakes": "no missed questions found.", "course": "this course has no questions yet."}[payload.source]
        )

    random.shuffle(question_ids)
    selected = question_ids[: payload.limit]

    session = PracticeSession(student_id=user.id, course_id=payload.course_id, source=payload.source,
                               question_order=[str(q) for q in selected])
    db.add(session)
    await db.commit()
    await db.refresh(session)

    result = await db.execute(select(Question).where(Question.id.in_(selected)).options(selectinload(Question.options)))
    questions = {q.id: q for q in result.scalars().all()}
    ordered = [questions[qid] for qid in selected if qid in questions]
    return PracticeSessionStartOut(id=session.id, source=session.source, course_id=session.course_id,
                                    questions=[PracticeQuestionOut.model_validate(q) for q in ordered])


@router.get("/practice/sessions/{session_id}/questions", response_model=list[PracticeQuestionOut])
async def get_practice_session_questions(
    session_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-fetches the question set for an in-progress session — lets the
    practice-taking page survive a refresh without losing state, the same
    resume pattern GET /exams/attempts/{id}/questions provides for exams."""
    session = await db.get(PracticeSession, session_id)
    if session is None or session.student_id != user.id:
        raise NotFoundError("Practice session not found.")
    question_ids = [uuid.UUID(q) for q in session.question_order]
    result = await db.execute(select(Question).where(Question.id.in_(question_ids)).options(selectinload(Question.options)))
    questions = {q.id: q for q in result.scalars().all()}
    ordered = [questions[qid] for qid in question_ids if qid in questions]
    return [PracticeQuestionOut.model_validate(q) for q in ordered]


@router.post("/practice/sessions/{session_id}/submit", response_model=PracticeResultOut)
async def submit_practice_session(
    session_id: uuid.UUID,
    payload: PracticeSubmit,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(PracticeSession, session_id)
    if session is None or session.student_id != user.id:
        raise NotFoundError("Practice session not found.")
    if session.submitted_at is not None:
        return await _practice_result(db, session)

    points_earned, points_possible = 0, 0
    answer_outs: list[PracticeAnswerResultOut] = []
    for ans in payload.answers:
        question = (await db.execute(
            select(Question).where(Question.id == ans.question_id).options(selectinload(Question.options))
        )).scalar_one_or_none()
        if question is None:
            continue
        selected_ids = [str(i) for i in ans.selected_option_ids]
        is_correct, points = grade_answer(question, selected_ids, ans.text_answer)
        points_earned += points
        points_possible += question.points
        db.add(PracticeAnswer(session_id=session.id, question_id=question.id, selected_option_ids=selected_ids,
                               text_answer=ans.text_answer, is_correct=is_correct, points_awarded=points))
        answer_outs.append(PracticeAnswerResultOut(
            question_id=question.id, prompt=question.prompt, is_correct=is_correct,
            selected_option_ids=ans.selected_option_ids,
            correct_option_ids=[o.id for o in question.options if o.is_correct],
            explanation=question.explanation,
        ))

    score_percent, _ = summarize_attempt(points_earned, points_possible, 0)
    session.points_earned = points_earned
    session.points_possible = points_possible
    session.score_percent = score_percent
    session.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)

    return PracticeResultOut(id=session.id, source=session.source, score_percent=score_percent,
                              points_earned=points_earned, points_possible=points_possible,
                              submitted_at=session.submitted_at, answers=answer_outs)


async def _practice_result(db: AsyncSession, session: PracticeSession) -> PracticeResultOut:
    answers = (await db.execute(select(PracticeAnswer).where(PracticeAnswer.session_id == session.id))).scalars().all()
    answer_outs = []
    for a in answers:
        question = (await db.execute(
            select(Question).where(Question.id == a.question_id).options(selectinload(Question.options))
        )).scalar_one_or_none()
        if question is None:
            continue
        answer_outs.append(PracticeAnswerResultOut(
            question_id=a.question_id, prompt=question.prompt, is_correct=bool(a.is_correct),
            selected_option_ids=[uuid.UUID(i) for i in a.selected_option_ids],
            correct_option_ids=[o.id for o in question.options if o.is_correct],
            explanation=question.explanation,
        ))
    return PracticeResultOut(id=session.id, source=session.source, score_percent=session.score_percent or 0,
                              points_earned=session.points_earned or 0, points_possible=session.points_possible or 0,
                              submitted_at=session.submitted_at, answers=answer_outs)


@router.get("/practice/sessions/{session_id}", response_model=PracticeResultOut)
async def get_practice_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(PracticeSession, session_id)
    if session is None or session.student_id != user.id:
        raise NotFoundError("Practice session not found.")
    if session.submitted_at is None:
        raise ConflictError("This practice session hasn't been submitted yet.")
    return await _practice_result(db, session)


@router.get("/practice/me/sessions", response_model=list[PracticeSessionHistoryOut])
async def my_practice_sessions(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(PracticeSession).where(PracticeSession.student_id == user.id).order_by(PracticeSession.started_at.desc())
    )).scalars().all()
    out = []
    for s in rows:
        course = await db.get(Course, s.course_id) if s.course_id else None
        out.append(PracticeSessionHistoryOut(id=s.id, source=s.source, course_id=s.course_id,
                                              course_title=course.title if course else None,
                                              score_percent=s.score_percent, started_at=s.started_at, submitted_at=s.submitted_at))
    return out
