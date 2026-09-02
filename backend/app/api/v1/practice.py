from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_verified_user
from app.models.assessment import Question
from app.models.contest import ContestAnswer, ContestAttempt
from app.models.elimination import EliminationAnswer, EliminationParticipant
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

    return BookmarkOut(id=existing.id, question_id=question_id, prompt=question.prompt, question_type=question.question_type,
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
    if not rows:
        return []

    question_ids = {b.question_id for b in rows}
    questions_by_id = {q.id: q for q in (await db.execute(select(Question).where(Question.id.in_(question_ids)))).scalars().all()}

    out = []
    for b in rows:
        question = questions_by_id.get(b.question_id)
        if question is None:
            continue
        out.append(BookmarkOut(id=b.id, question_id=b.question_id, prompt=question.prompt, question_type=question.question_type,
                                note=b.note, created_at=b.created_at))
    return out


async def _mistake_question_ids(db: AsyncSession, student_id: uuid.UUID) -> list[uuid.UUID]:
    """Every question this student has ever answered incorrectly across a
    submitted contest attempt or an elimination-battle round, deduplicated,
    most-recent first."""
    contest_stmt = (
        select(ContestAnswer.question_id, ContestAnswer.created_at)
        .join(ContestAttempt, ContestAttempt.id == ContestAnswer.attempt_id)
        .where(ContestAttempt.student_id == student_id, ContestAnswer.is_correct.is_(False))
    )
    elimination_stmt = (
        select(EliminationAnswer.round_id, EliminationAnswer.created_at)
        .join(EliminationParticipant, EliminationParticipant.id == EliminationAnswer.participant_id)
        .where(EliminationParticipant.user_id == student_id, EliminationAnswer.is_correct.is_(False))
    )
    contest_rows = (await db.execute(contest_stmt)).all()
    elimination_rows = (await db.execute(elimination_stmt)).all()

    # EliminationAnswer references a round, not a question directly — resolve
    # via EliminationRound.question_id in a second pass rather than a more
    # complex join, since this path is rarely hit (most eliminations are a
    # single wrong answer, not a large history to page through).
    from app.models.elimination import EliminationRound
    elim_round_ids = [round_id for round_id, _ in elimination_rows]
    elim_question_by_round = {}
    if elim_round_ids:
        elim_question_by_round = dict((await db.execute(
            select(EliminationRound.id, EliminationRound.question_id).where(EliminationRound.id.in_(elim_round_ids))
        )).all())

    by_id: dict[uuid.UUID, datetime] = {}
    for qid, created_at in contest_rows:
        if qid not in by_id or created_at > by_id[qid]:
            by_id[qid] = created_at
    for round_id, created_at in elimination_rows:
        qid = elim_question_by_round.get(round_id)
        if qid is not None and (qid not in by_id or created_at > by_id[qid]):
            by_id[qid] = created_at
    return [qid for qid, _ in sorted(by_id.items(), key=lambda kv: kv[1], reverse=True)]


@router.post("/practice/sessions", response_model=PracticeSessionStartOut, status_code=201)
async def start_practice_session(
    payload: PracticeStartRequest,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.source == "bookmarks":
        question_ids = list((await db.execute(
            select(QuestionBookmark.question_id).where(QuestionBookmark.student_id == user.id)
        )).scalars().all())
    elif payload.source == "mistakes":
        question_ids = await _mistake_question_ids(db, user.id)
    else:
        raise ValidationAppError("Unknown practice source.")

    if not question_ids:
        raise NotFoundError(
            "Nothing to practice yet — "
            + {"bookmarks": "bookmark a question first.", "mistakes": "no missed questions found."}[payload.source]
        )

    random.shuffle(question_ids)
    selected = question_ids[: payload.limit]

    session = PracticeSession(student_id=user.id, source=payload.source, question_order=[str(q) for q in selected])
    db.add(session)
    await db.commit()
    await db.refresh(session)

    result = await db.execute(select(Question).where(Question.id.in_(selected)).options(selectinload(Question.options)))
    questions = {q.id: q for q in result.scalars().all()}
    ordered = [questions[qid] for qid in selected if qid in questions]
    return PracticeSessionStartOut(id=session.id, source=session.source, questions=[PracticeQuestionOut.model_validate(q) for q in ordered])


@router.get("/practice/sessions/{session_id}/questions", response_model=list[PracticeQuestionOut])
async def get_practice_session_questions(
    session_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
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

    # Grade every question in the session's own fixed question_order (set
    # once when the session was created, never client-controlled) — not
    # just whatever question_ids happen to appear in payload.answers.
    # PracticeSubmit.answers has no completeness requirement, so a payload
    # that simply omits a question the student doesn't know used to make
    # points_possible shrink to match only what they chose to answer,
    # inflating score_percent (same bug fixed in contests.py's
    # submit_contest_attempt — see that commit for the full explanation).
    # A question missing from the payload is graded as unanswered (0 points).
    all_question_ids = [uuid.UUID(q) for q in session.question_order]
    questions_by_id = {
        q.id: q for q in (await db.execute(
            select(Question).where(Question.id.in_(all_question_ids)).options(selectinload(Question.options))
        )).scalars().all()
    } if all_question_ids else {}
    answers_by_qid = {ans.question_id: ans for ans in payload.answers}

    points_earned, points_possible = 0, 0
    answer_outs: list[PracticeAnswerResultOut] = []
    for qid in all_question_ids:
        question = questions_by_id.get(qid)
        if question is None:
            continue
        ans = answers_by_qid.get(qid)
        selected_ids = [str(i) for i in ans.selected_option_ids] if ans else []
        text_answer = ans.text_answer if ans else None
        is_correct, points = grade_answer(question, selected_ids, text_answer)
        points_earned += points
        points_possible += question.points
        db.add(PracticeAnswer(session_id=session.id, question_id=question.id, selected_option_ids=selected_ids,
                               text_answer=text_answer, is_correct=is_correct, points_awarded=points))
        answer_outs.append(PracticeAnswerResultOut(
            question_id=question.id, prompt=question.prompt, is_correct=is_correct,
            selected_option_ids=[uuid.UUID(i) for i in selected_ids],
            correct_option_ids=[o.id for o in question.options if o.is_correct],
            explanation=question.explanation,
        ))

    score_percent, _ = summarize_attempt(points_earned, points_possible, 0)
    session.points_earned = points_earned
    session.points_possible = points_possible
    session.score_percent = score_percent
    session.submitted_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(session)

    return PracticeResultOut(id=session.id, source=session.source, score_percent=score_percent,
                              points_earned=points_earned, points_possible=points_possible,
                              submitted_at=session.submitted_at, answers=answer_outs)


async def _practice_result(db: AsyncSession, session: PracticeSession) -> PracticeResultOut:
    answers = (await db.execute(select(PracticeAnswer).where(PracticeAnswer.session_id == session.id))).scalars().all()
    answer_qids = {a.question_id for a in answers}
    questions_by_id = {
        q.id: q for q in (await db.execute(
            select(Question).where(Question.id.in_(answer_qids)).options(selectinload(Question.options))
        )).scalars().all()
    } if answer_qids else {}
    answer_outs = []
    for a in answers:
        question = questions_by_id.get(a.question_id)
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
    return [
        PracticeSessionHistoryOut(id=s.id, source=s.source, score_percent=s.score_percent, started_at=s.started_at, submitted_at=s.submitted_at)
        for s in rows
    ]
