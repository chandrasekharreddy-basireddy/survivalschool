from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.dependencies import get_current_verified_user, require_permission
from app.models.lms import Course, CourseProgress, CourseSection, Lesson, LessonProgress
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.lms import LessonCreate, LessonOut
from app.services.analytics_service import track_event
from app.services.certificate_service import issue_certificate
from app.services.email_service import send_email
from app.services.gamification_service import (
    POINTS_LESSON_COMPLETE,
    award_points,
    evaluate_and_award_badges,
    record_daily_activity,
)
from app.services.n8n_service import emit_event

router = APIRouter(prefix="/lessons", tags=["lessons"])


@router.post("/sections/{section_id}", response_model=LessonOut, status_code=201)
async def create_lesson(
    section_id: uuid.UUID,
    payload: LessonCreate,
    user: User = Depends(require_permission("lessons.manage")),
    db: AsyncSession = Depends(get_db),
):
    section = await db.get(CourseSection, section_id)
    if section is None:
        raise NotFoundError("Section not found.")
    lesson = Lesson(section_id=section_id, **payload.model_dump())
    db.add(lesson)
    await db.commit()
    await db.refresh(lesson)
    return LessonOut.model_validate(lesson)


async def _recalculate_course_progress(db: AsyncSession, student_id: uuid.UUID, course_id: uuid.UUID) -> CourseProgress:
    lessons_total = (await db.execute(
        select(func.count(Lesson.id)).join(CourseSection).where(CourseSection.course_id == course_id)
    )).scalar_one()
    lessons_completed = (await db.execute(
        select(func.count(LessonProgress.id))
        .join(Lesson, Lesson.id == LessonProgress.lesson_id)
        .join(CourseSection, CourseSection.id == Lesson.section_id)
        .where(CourseSection.course_id == course_id, LessonProgress.student_id == student_id, LessonProgress.is_completed.is_(True))
    )).scalar_one()

    progress = (await db.execute(
        select(CourseProgress).where(CourseProgress.student_id == student_id, CourseProgress.course_id == course_id)
    )).scalar_one_or_none()
    if progress is None:
        progress = CourseProgress(student_id=student_id, course_id=course_id)
        db.add(progress)

    progress.lessons_total = lessons_total
    progress.lessons_completed = lessons_completed
    progress.percent_complete = round((lessons_completed / lessons_total) * 100) if lessons_total else 0
    await db.flush()
    return progress


@router.post("/{lesson_id}/complete", response_model=MessageResponse)
async def complete_lesson(
    lesson_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise NotFoundError("Lesson not found.")
    section = await db.get(CourseSection, lesson.section_id)
    course = await db.get(Course, section.course_id)

    existing = (await db.execute(
        select(LessonProgress).where(LessonProgress.student_id == user.id, LessonProgress.lesson_id == lesson_id)
    )).scalar_one_or_none()
    is_first_lesson = existing is None or not existing.is_completed

    if existing is None:
        existing = LessonProgress(student_id=user.id, lesson_id=lesson_id)
        db.add(existing)
    if not existing.is_completed:
        existing.is_completed = True
        existing.completed_at = datetime.now(timezone.utc)
        await award_points(db, user.id, POINTS_LESSON_COMPLETE, reason="lesson_complete", reference_id=lesson_id)
        await evaluate_and_award_badges(db, user.id, "lesson_complete", {"is_first_lesson": is_first_lesson})
        streak = await record_daily_activity(db, user.id)
        await evaluate_and_award_badges(db, user.id, "streak", {"current_streak_days": streak.current_streak_days})

    progress = await _recalculate_course_progress(db, user.id, course.id)

    course_just_completed = False
    if progress.percent_complete == 100:
        from app.models.lms import Enrollment
        enrollment = (await db.execute(
            select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.course_id == course.id)
        )).scalar_one_or_none()
        if enrollment and enrollment.status != "completed":
            enrollment.status = "completed"
            enrollment.completed_at = datetime.now(timezone.utc)
            course_just_completed = True

    await track_event(db, event_type="lesson_completed", user_id=user.id, metadata={"lesson_id": str(lesson_id)})

    if course_just_completed:
        from app.services.gamification_service import POINTS_COURSE_COMPLETE
        await award_points(db, user.id, POINTS_COURSE_COMPLETE, reason="course_complete", reference_id=course.id)
        await evaluate_and_award_badges(db, user.id, "course_complete", {})
        cert = await issue_certificate(db, user, course)
        await track_event(db, event_type="certificate_issued", user_id=user.id, metadata={"course_id": str(course.id)})
        await db.commit()
        from app.services.certificate_service import verification_url
        await send_email(
            user.email, "Certificate earned", "certificate_issued",
            full_name=user.full_name, course_title=course.title,
            certificate_url=f"/certificates/{cert.certificate_number}",
            certificate_number=cert.certificate_number,
            verify_url=verification_url(cert.certificate_number),
        )
        await emit_event("certificate.issued", {
            "email": user.email, "full_name": user.full_name,
            "course_title": course.title, "certificate_number": cert.certificate_number,
        })
    else:
        await db.commit()

    return MessageResponse(message="Lesson marked complete.")
