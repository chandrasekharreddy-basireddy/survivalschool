"""Shared "free-text subject/topic -> real taxonomy row -> AI-generated
question pool" pipeline, used by both the AI Weekly Exam (ai_exam_service.py)
and elimination battles (elimination_service.py) — the two places in the app
that let a student type a subject/topic instead of picking from an
instructor-curated one."""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Question, QuestionOption
from app.models.exam_platform import Subject, Topic, University
from app.services.ai_provider import get_ai_provider
from app.services.question_validation_service import validate_generated_batch


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:140] or "topic"


async def _get_or_create_university(db: AsyncSession) -> University:
    university = (await db.execute(select(University).where(University.singleton.is_(True)))).scalar_one_or_none()
    if university is None:
        university = University(name="Sai University")
        db.add(university)
        await db.flush()
    return university


async def find_or_create_subject(db: AsyncSession, name: str) -> Subject:
    """Subjects/topics are normally admin-curated (system.manage), but a
    freely-typed subject/topic (AI Weekly Exam registration, elimination
    battle creation) creates the taxonomy row transparently on first use
    rather than bouncing the student through an admin-only endpoint.
    Matched case-insensitively by slug so "Data Structures" and
    "data structures" resolve to the same row."""
    slug = slugify(name)
    university = await _get_or_create_university(db)
    existing = (await db.execute(
        select(Subject).where(Subject.university_id == university.id, Subject.slug == slug)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    subject = Subject(university_id=university.id, name=name.strip()[:150], slug=slug)
    try:
        async with db.begin_nested():
            db.add(subject)
            await db.flush()
    except IntegrityError:
        subject = (await db.execute(
            select(Subject).where(Subject.university_id == university.id, Subject.slug == slug)
        )).scalar_one()
    return subject


async def find_or_create_topic(db: AsyncSession, subject_id: uuid.UUID, name: str) -> Topic:
    slug = slugify(name)
    existing = (await db.execute(
        select(Topic).where(Topic.subject_id == subject_id, Topic.slug == slug)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    topic = Topic(subject_id=subject_id, name=name.strip()[:150], slug=slug)
    try:
        async with db.begin_nested():
            db.add(topic)
            await db.flush()
    except IntegrityError:
        topic = (await db.execute(
            select(Topic).where(Topic.subject_id == subject_id, Topic.slug == slug)
        )).scalar_one()
    return topic


async def generate_and_persist_questions(topic: Topic, single_count: int, multiple_count: int) -> list[uuid.UUID]:
    """Runs in its own AsyncSessionLocal() — the AI call can take a while,
    and callers with their own open transaction shouldn't hold a connection
    idle for it. Callers must already have committed topic (and its
    subject) so this separate session can see the FK target — see the
    commit right before this is called in both callers."""
    provider = get_ai_provider()
    generated = await provider.generate_mixed_questions(topic.name, single_count, multiple_count)
    validate_generated_batch(generated)

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        question_ids: list[uuid.UUID] = []
        for gq in generated:
            question = Question(
                subject_id=topic.subject_id, topic_id=topic.id, prompt=gq.prompt,
                question_type=gq.question_type, is_ai_generated=True, is_validated=True,
            )
            db.add(question)
            await db.flush()
            for idx, (text, is_correct) in enumerate(gq.options):
                db.add(QuestionOption(question_id=question.id, text=text, is_correct=is_correct, order_index=idx))
            question_ids.append(question.id)
        await db.commit()
    return question_ids
