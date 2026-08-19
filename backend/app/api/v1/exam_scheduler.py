from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.dependencies import require_course_ownership, require_permission
from app.models.scheduling import ScheduledExamConfig
from app.models.user import User

router = APIRouter(prefix="/exams", tags=["exams"])


class ScheduledExamConfigIn(BaseModel):
    day_of_week: int = Field(ge=5, le=6, description="Saturday=5, Sunday=6")
    time_slot: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    duration_minutes: int = Field(ge=15, le=240)
    question_count: int = Field(ge=1, le=50)
    auto_certificate_top_n: int = Field(ge=0, le=10)
    course_id: uuid.UUID
    difficulty: str = Field(default="mixed", max_length=30)
    title_prefix: str = Field(default="Weekend AI Exam", max_length=120)
    is_active: bool = True


class ScheduledExamConfigOut(ScheduledExamConfigIn):
    id: uuid.UUID
    last_occurrence_key: str | None

    model_config = {"from_attributes": True}


@router.get("/schedules", response_model=list[ScheduledExamConfigOut])
async def list_schedules(user: User = Depends(require_permission("exam.manage")), db: AsyncSession = Depends(get_db)):
    stmt = select(ScheduledExamConfig).order_by(ScheduledExamConfig.day_of_week, ScheduledExamConfig.time_slot)
    # exam.manage is granted to every INSTRUCTOR — without this filter, any
    # instructor could see every other instructor's weekend-exam schedules
    # (including which courses they run and at what times).
    if not user.has_permission("system.manage"):
        from app.models.lms import Course

        stmt = stmt.join(Course, Course.id == ScheduledExamConfig.course_id).where(Course.instructor_id == user.id)
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.post("/schedules", response_model=ScheduledExamConfigOut, status_code=201)
async def create_schedule(payload: ScheduledExamConfigIn, user: User = Depends(require_permission("exam.manage")), db: AsyncSession = Depends(get_db)):
    # exam.manage is granted to every INSTRUCTOR — without this, any
    # instructor could wire up weekend AI exams for any other instructor's
    # course.
    await require_course_ownership(db, user, payload.course_id)
    config = ScheduledExamConfig(**payload.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@router.patch("/schedules/{schedule_id}", response_model=ScheduledExamConfigOut)
async def update_schedule(schedule_id: uuid.UUID, payload: ScheduledExamConfigIn, user: User = Depends(require_permission("exam.manage")), db: AsyncSession = Depends(get_db)):
    config = await db.get(ScheduledExamConfig, schedule_id)
    if config is None:
        raise NotFoundError("Scheduled exam configuration not found.")
    # Must own the course the schedule currently belongs to...
    await require_course_ownership(db, user, config.course_id)
    # ...and, since the payload can repoint course_id entirely, also own the
    # target course if it's being changed (otherwise an instructor could
    # reassign their own schedule row onto someone else's course).
    if payload.course_id != config.course_id:
        await require_course_ownership(db, user, payload.course_id)
    for key, value in payload.model_dump().items():
        setattr(config, key, value)
    await db.commit()
    await db.refresh(config)
    return config
