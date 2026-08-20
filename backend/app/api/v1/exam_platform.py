"""Subject/Topic taxonomy CRUD, plus the topic difficulty check the AI Weekly
Exam registration flow depends on (see ai_exam_service.py)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.exam_platform import Subject, Topic, University
from app.models.user import User
from app.schemas.exam_platform import (
    SubjectCreate,
    SubjectOut,
    TopicCreate,
    TopicDifficultyOut,
    TopicOut,
)
from app.services.difficulty_service import (
    MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM,
    get_current_difficulty,
)

router = APIRouter(tags=["exam-platform"])


async def _get_or_create_university(db: AsyncSession) -> University:
    university = (await db.execute(select(University).where(University.singleton.is_(True)))).scalar_one_or_none()
    if university is None:
        university = University(name="Sai University")
        db.add(university)
        await db.flush()
    return university


@router.get("/subjects", response_model=list[SubjectOut])
async def list_subjects(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Subject).where(Subject.is_active.is_(True)).order_by(Subject.name))).scalars().all()
    return rows


@router.post("/subjects", response_model=SubjectOut, status_code=201)
async def create_subject(payload: SubjectCreate, user: User = Depends(require_permission("system.manage")), db: AsyncSession = Depends(get_db)):
    university = await _get_or_create_university(db)
    subject = Subject(university_id=university.id, name=payload.name, slug=payload.slug, description=payload.description)
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject


@router.get("/subjects/{subject_id}/topics", response_model=list[TopicOut])
async def list_topics(subject_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Topic).where(Topic.subject_id == subject_id, Topic.is_active.is_(True)).order_by(Topic.name)
    )).scalars().all()
    return rows


@router.post("/subjects/{subject_id}/topics", response_model=TopicOut, status_code=201)
async def create_topic(subject_id: uuid.UUID, payload: TopicCreate, user: User = Depends(require_permission("system.manage")), db: AsyncSession = Depends(get_db)):
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise NotFoundError("Subject not found.")
    topic = Topic(subject_id=subject_id, name=payload.name, slug=payload.slug, description=payload.description)
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return topic


@router.get("/topics/{topic_id}/difficulty", response_model=TopicDifficultyOut)
async def topic_difficulty(topic_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise NotFoundError("Topic not found.")
    evaluation = await get_current_difficulty(db, topic_id)
    await db.commit()
    return TopicDifficultyOut(
        topic_id=topic_id, difficulty_percent=evaluation.difficulty_percent,
        formula_version=evaluation.formula_version, reason=evaluation.reason, sample_size=evaluation.sample_size,
        eligible_for_ai_exam=evaluation.difficulty_percent >= MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM,
    )
