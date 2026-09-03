"""The shared question bank — feeds contests (AI weekly exam), elimination
battles, and ai_practice. Not course-scoped (there are no courses); gated
by permission only, tagged by subject/topic instead of owned by an
instructor's course.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.database import get_db
from app.dependencies import require_permission
from app.models.assessment import Question, QuestionOption
from app.models.system import AuditLog
from app.models.user import User
from app.schemas.assessment import QuestionCreate, QuestionOut
from app.schemas.question_import import ImportPreviewOut, ImportRowOut
from app.services.audit_service import record_audit_event
from app.services.question_import_service import commit_rows, parse_csv, parse_xlsx

router = APIRouter(prefix="/questions", tags=["question-bank"])


class MyQuestionStatsOut(BaseModel):
    questions_created: int


@router.get("/me/stats", response_model=MyQuestionStatsOut)
async def my_question_stats(
    user: User = Depends(require_permission("quiz.create", "exam.manage")),
    db: AsyncSession = Depends(get_db),
):
    """A lecturer's own contribution count to the shared question bank —
    there's no per-instructor ownership on Question itself (the bank is
    genuinely shared, not course-scoped, see this module's docstring), so
    this is derived from the audit trail instead: one question.create event
    per single question, plus the inserted_count on each question.
    bulk_import event (bulk rows are logged as one event per batch, not one
    per row — see bulk_import_questions above)."""
    single_count = (await db.execute(
        select(AuditLog).where(AuditLog.actor_id == user.id, AuditLog.action == "question.create", AuditLog.result == "success")
    )).scalars().all()
    bulk_events = (await db.execute(
        select(AuditLog).where(AuditLog.actor_id == user.id, AuditLog.action == "question.bulk_import", AuditLog.result == "success")
    )).scalars().all()
    bulk_count = sum((e.metadata_json or {}).get("inserted_count", 0) for e in bulk_events)
    return MyQuestionStatsOut(questions_created=len(single_count) + bulk_count)


@router.post("", response_model=QuestionOut, status_code=201)
async def create_question(
    payload: QuestionCreate,
    user: User = Depends(require_permission("quiz.create", "exam.manage")),
    db: AsyncSession = Depends(get_db),
):
    if payload.question_type in ("single", "true_false") and sum(1 for o in payload.options if o.is_correct) != 1:
        raise ValidationAppError("single/true_false questions must have exactly one correct option.")
    if payload.question_type == "multiple" and sum(1 for o in payload.options if o.is_correct) < 1:
        raise ValidationAppError("multiple-answer questions need at least one correct option.")

    question = Question(
        subject_id=payload.subject_id, topic_id=payload.topic_id, prompt=payload.prompt,
        question_type=payload.question_type, points=payload.points,
        explanation=payload.explanation, short_answer_key=payload.short_answer_key,
    )
    db.add(question)
    await db.flush()
    for opt in payload.options:
        db.add(QuestionOption(question_id=question.id, text=opt.text, is_correct=opt.is_correct, order_index=opt.order_index))
    await record_audit_event(db, actor_id=user.id, action="question.create", resource_type="question", resource_id=str(question.id))
    await db.commit()
    return question


@router.post("/bulk-import", response_model=ImportPreviewOut)
async def bulk_import_questions(
    subject_id: uuid.UUID,
    topic_id: uuid.UUID,
    dry_run: bool = Query(True, description="Preview only (default). Pass dry_run=false to actually commit, and only once every row is error-free."),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("quiz.create", "exam.manage")),
    db: AsyncSession = Depends(get_db),
):
    """CSV or XLSX bulk question import — see app/services/question_import_service.py
    for the expected column format. All-or-nothing: a commit (dry_run=false)
    only writes anything if every row in the file is valid; otherwise nothing
    is inserted and the same per-row errors are returned so the caller can
    fix the file and re-upload."""
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
        inserted_count = await commit_rows(db, subject_id, topic_id, rows)
        committed = True
        await record_audit_event(db, actor_id=user.id, action="question.bulk_import", resource_type="topic",
                                  resource_id=str(topic_id), metadata={"inserted_count": inserted_count})

    return ImportPreviewOut(
        total_rows=len(rows), valid_rows=len(rows) - len(error_rows), error_rows=len(error_rows),
        rows=[ImportRowOut(row_number=r.row_number, prompt=r.prompt, question_type=r.question_type, error=r.error) for r in rows],
        committed=committed, inserted_count=inserted_count,
    )
