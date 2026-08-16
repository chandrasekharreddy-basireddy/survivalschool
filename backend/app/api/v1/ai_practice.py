from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_verified_user
from app.models.ai_practice import AIGeneratedQuestion, AIGeneratedQuestionOption, AIMockAnswer, AIMockSession
from app.models.user import User
from app.schemas.ai_practice import (
    AIMockAnswerResultOut,
    AIMockResultOut,
    AIMockSessionCreate,
    AIMockSessionHistoryOut,
    AIMockSessionOut,
    AIMockSubmit,
)
from app.services.ai_provider import AIGenerationError, get_ai_provider
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter(prefix="/ai-practice", tags=["ai-practice"])


class AIExplanationOut(BaseModel):
    question_id: uuid.UUID
    explanation: str
    provider: str


@router.post("/sessions", response_model=AIMockSessionOut, status_code=201)
async def create_ai_mock_session(payload: AIMockSessionCreate, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Generates a fresh set of AI-authored MCQs for the given subject.
    These are stored in ai_generated_questions — a table structurally
    separate from the real `questions` bank — and are never eligible for a
    quiz, exam, or contest. Rate-limited since each call is a real
    (or mock) AI generation request."""
    await enforce_rate_limit(f"ai-mock-generate:{user.id}", limit=10, window_seconds=3600)

    provider = get_ai_provider()
    try:
        generated = await provider.generate_questions(payload.subject, payload.question_count)
    except AIGenerationError as exc:
        raise ConflictError(f"Couldn't generate practice questions right now: {exc}") from exc

    if not generated:
        raise ConflictError("The AI provider didn't return any usable questions. Try again.")

    session = AIMockSession(student_id=user.id, subject=payload.subject, question_count=len(generated), provider=provider.name)
    db.add(session)
    await db.flush()

    for idx, mcq in enumerate(generated):
        question = AIGeneratedQuestion(session_id=session.id, prompt=mcq.prompt, order_index=idx)
        db.add(question)
        await db.flush()
        for opt_idx, (text, is_correct) in enumerate(mcq.options):
            db.add(AIGeneratedQuestionOption(question_id=question.id, text=text, is_correct=is_correct, order_index=opt_idx))

    await db.commit()
    result = await db.execute(
        select(AIMockSession).where(AIMockSession.id == session.id)
        .options(selectinload(AIMockSession.questions).selectinload(AIGeneratedQuestion.options))
    )
    return result.scalar_one()


@router.get("/sessions/{session_id}/questions", response_model=AIMockSessionOut)
async def get_ai_mock_session_questions(session_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AIMockSession).where(AIMockSession.id == session_id)
        .options(selectinload(AIMockSession.questions).selectinload(AIGeneratedQuestion.options))
    )
    session = result.scalar_one_or_none()
    if session is None or session.student_id != user.id:
        raise NotFoundError("Practice session not found.")
    if session.submitted_at is not None:
        raise ConflictError("This session has already been submitted — fetch the result instead.")
    return session


@router.post("/sessions/{session_id}/submit", response_model=AIMockResultOut)
async def submit_ai_mock_session(session_id: uuid.UUID, payload: AIMockSubmit, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Graded server-side against the stored is_correct flags — same
    never-trust-the-client principle as every other assessment path, even
    though the answer key here came from an AI generation rather than an
    instructor. Awards zero gamification points, same as bookmarked/mistake
    practice mode — this is for learning, not for score."""
    result = await db.execute(
        select(AIMockSession).where(AIMockSession.id == session_id)
        .options(selectinload(AIMockSession.questions).selectinload(AIGeneratedQuestion.options))
    )
    session = result.scalar_one_or_none()
    if session is None or session.student_id != user.id:
        raise NotFoundError("Practice session not found.")
    if session.submitted_at is not None:
        raise ConflictError("This session has already been submitted.")

    questions_by_id = {q.id: q for q in session.questions}
    submitted_by_qid = {a.question_id: a for a in payload.answers}
    if not submitted_by_qid:
        raise ValidationAppError("At least one answer is required.")

    correct_count = 0
    answer_results: list[AIMockAnswerResultOut] = []
    for question in session.questions:
        ans = submitted_by_qid.get(question.id)
        selected = [str(o) for o in (ans.selected_option_ids if ans else [])]
        correct_ids = {str(o.id) for o in question.options if o.is_correct}
        is_correct = set(selected) == correct_ids and len(correct_ids) > 0
        if is_correct:
            correct_count += 1
        db.add(AIMockAnswer(session_id=session.id, question_id=question.id, selected_option_ids=selected, is_correct=is_correct))
        answer_results.append(AIMockAnswerResultOut(
            question_id=question.id, prompt=question.prompt, is_correct=is_correct,
            selected_option_ids=[uuid.UUID(s) for s in selected],
            correct_option_ids=[o.id for o in question.options if o.is_correct],
        ))

    score_percent = round((correct_count / len(questions_by_id)) * 100) if questions_by_id else 0
    session.submitted_at = datetime.now(timezone.utc)
    session.score_percent = score_percent
    await db.commit()

    return AIMockResultOut(id=session.id, subject=session.subject, score_percent=score_percent, answers=answer_results)


@router.post("/sessions/{session_id}/questions/{question_id}/explanation", response_model=AIExplanationOut)
async def explain_ai_mock_question(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates an AI explanation only after submission, using the server's
    stored question, selected answer, and correct answer. The client cannot
    provide or alter the answer key."""
    await enforce_rate_limit(f"ai-explain:{user.id}", limit=30, window_seconds=3600)

    result = await db.execute(
        select(AIMockSession).where(AIMockSession.id == session_id)
        .options(selectinload(AIMockSession.questions).selectinload(AIGeneratedQuestion.options))
    )
    session = result.scalar_one_or_none()
    if session is None or session.student_id != user.id:
        raise NotFoundError("Practice session not found.")
    if session.submitted_at is None:
        raise ConflictError("Submit the practice session before requesting an AI explanation.")

    question = next((q for q in session.questions if q.id == question_id), None)
    if question is None:
        raise NotFoundError("Practice question not found.")

    answer_result = await db.execute(
        select(AIMockAnswer).where(
            AIMockAnswer.session_id == session.id,
            AIMockAnswer.question_id == question.id,
        )
    )
    answer = answer_result.scalar_one_or_none()
    selected_ids = set(answer.selected_option_ids if answer else [])
    selected_text = [o.text for o in question.options if str(o.id) in selected_ids]
    correct_text = [o.text for o in question.options if o.is_correct]

    provider = get_ai_provider()
    response = await provider.chat(
        [{
            "role": "user",
            "content": (
                f"Question: {question.prompt}\n"
                f"Student answer: {', '.join(selected_text) or 'No answer selected'}\n"
                f"Correct answer: {', '.join(correct_text)}\n"
                "Explain why the correct answer is right, why the student's answer is right or wrong, "
                "and give one practical coding takeaway."
            ),
        }],
        system_prompt=(
            "You are a coding practice tutor. Explain the supplied multiple-choice programming question "
            "clearly and briefly. Focus on the underlying coding concept. Do not invent facts or change the "
            "provided answer key."
        ),
    )
    if response.error or not response.content:
        raise ConflictError("The AI explanation is unavailable right now. Please try again.")

    return AIExplanationOut(question_id=question.id, explanation=response.content, provider=response.provider)


@router.get("/sessions/{session_id}", response_model=AIMockResultOut)
async def get_ai_mock_session_result(session_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AIMockSession).where(AIMockSession.id == session_id)
        .options(selectinload(AIMockSession.questions).selectinload(AIGeneratedQuestion.options))
    )
    session = result.scalar_one_or_none()
    if session is None or session.student_id != user.id:
        raise NotFoundError("Practice session not found.")
    if session.submitted_at is None:
        raise ConflictError("This session hasn't been submitted yet.")

    answers_result = await db.execute(select(AIMockAnswer).where(AIMockAnswer.session_id == session.id))
    answers_by_qid = {a.question_id: a for a in answers_result.scalars().all()}
    answer_results = [
        AIMockAnswerResultOut(
            question_id=q.id, prompt=q.prompt, is_correct=bool(answers_by_qid[q.id].is_correct) if q.id in answers_by_qid else False,
            selected_option_ids=[uuid.UUID(s) for s in (answers_by_qid[q.id].selected_option_ids if q.id in answers_by_qid else [])],
            correct_option_ids=[o.id for o in q.options if o.is_correct],
        )
        for q in session.questions
    ]
    return AIMockResultOut(id=session.id, subject=session.subject, score_percent=session.score_percent or 0, answers=answer_results)


@router.get("/me/sessions", response_model=list[AIMockSessionHistoryOut])
async def my_ai_mock_sessions(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AIMockSession).where(AIMockSession.student_id == user.id).order_by(AIMockSession.created_at.desc())
    )
    return result.scalars().all()
