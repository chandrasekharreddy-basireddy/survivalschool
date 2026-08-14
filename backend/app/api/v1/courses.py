from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional, get_current_verified_user, require_permission
from app.models.assessment import Exam, Quiz
from app.models.lms import Course, CourseProgress, CourseSection, Enrollment, Lesson
from app.models.user import User
from app.schemas.assessment import ExamOut, QuizOut
from app.schemas.auth import MessageResponse
from app.schemas.lms import (
    CourseCreate,
    CourseDetailOut,
    CourseOut,
    CourseUpdate,
    EnrollmentOut,
    SectionCreate,
    SectionOut,
)
from app.services.analytics_service import track_event
from app.services.audit_service import record_audit_event
from app.services.email_service import send_email
from app.services.n8n_service import emit_event

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=list[CourseOut])
async def list_courses(
    response: Response,
    published_only: bool = Query(True),
    search: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Course).where(Course.deleted_at.is_(None))
    if published_only:
        stmt = stmt.where(Course.is_published.is_(True))
    else:
        # Unpublished courses can contain draft titles/descriptions an
        # instructor isn't ready to make public yet — never let this branch
        # be reachable anonymously, and even authenticated, only surface an
        # instructor's OWN drafts unless the caller can already read all
        # courses (courses.read / SUPER_ADMIN), matching the same
        # backend-enforced-authorization pattern used everywhere else here.
        if user is None:
            raise AuthenticationError("Sign in to view unpublished courses.")
        # Deliberately NOT gated on courses.read — every INSTRUCTOR has that
        # permission for legitimate, unrelated reasons, and it would let any
        # instructor browse every other instructor's unpublished drafts.
        # system.manage (ADMIN/SUPER_ADMIN only) is the actual "see everyone's
        # drafts" bar; anyone else only ever sees their own.
        if not (user.has_permission("system.manage") or user.has_role("SUPER_ADMIN")):
            stmt = stmt.where(Course.instructor_id == user.id)
    if search:
        stmt = stmt.where(Course.title.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    # Total count exposed via header (not the JSON body) so this stays a
    # backward-compatible array response for existing clients — the audit
    # flagged this endpoint as unbounded, not as needing an envelope change.
    response.headers["X-Total-Count"] = str(total)

    result = await db.execute(stmt.order_by(Course.created_at.desc()).limit(limit).offset(offset))
    return result.scalars().all()


@router.post("", response_model=CourseOut, status_code=201)
async def create_course(
    payload: CourseCreate,
    user: User = Depends(require_permission("courses.create")),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(Course).where(Course.slug == payload.slug))).scalar_one_or_none()
    if existing:
        raise ConflictError("A course with this slug already exists.")
    course = Course(**payload.model_dump(), instructor_id=user.id)
    db.add(course)
    await record_audit_event(db, actor_id=user.id, action="course.create", resource_type="course")
    await db.commit()
    await db.refresh(course)
    return course


@router.get("/{course_id}", response_model=CourseDetailOut)
async def get_course(course_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Course)
        .where(Course.id == course_id, Course.deleted_at.is_(None))
        .options(selectinload(Course.sections).selectinload(CourseSection.lessons))
    )
    course = result.scalar_one_or_none()
    if course is None:
        raise NotFoundError("Course not found.")
    return course


@router.get("/{course_id}/quizzes", response_model=list[QuizOut])
async def list_course_quizzes(course_id: uuid.UUID, published_only: bool = Query(True), db: AsyncSession = Depends(get_db)):
    stmt = select(Quiz).where(Quiz.course_id == course_id)
    if published_only:
        stmt = stmt.where(Quiz.is_published.is_(True))
    result = await db.execute(stmt.order_by(Quiz.created_at.asc()))
    return result.scalars().all()


@router.get("/{course_id}/exams", response_model=list[ExamOut])
async def list_course_exams(course_id: uuid.UUID, published_only: bool = Query(True), db: AsyncSession = Depends(get_db)):
    stmt = select(Exam).where(Exam.course_id == course_id)
    if published_only:
        stmt = stmt.where(Exam.is_published.is_(True))
    result = await db.execute(stmt.order_by(Exam.created_at.asc()))
    return result.scalars().all()


@router.patch("/{course_id}", response_model=CourseOut)
async def update_course(
    course_id: uuid.UUID,
    payload: CourseUpdate,
    user: User = Depends(require_permission("courses.update")),
    db: AsyncSession = Depends(get_db),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    await record_audit_event(db, actor_id=user.id, action="course.update", resource_type="course", resource_id=str(course_id))
    await db.commit()
    await db.refresh(course)
    return course


@router.post("/{course_id}/publish", response_model=CourseOut)
async def publish_course(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("courses.update")),
    db: AsyncSession = Depends(get_db),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    course.is_published = True
    await record_audit_event(db, actor_id=user.id, action="course.publish", resource_type="course", resource_id=str(course_id))
    await db.commit()
    await db.refresh(course)
    return course


@router.post("/{course_id}/unpublish", response_model=CourseOut)
async def unpublish_course(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("courses.update")),
    db: AsyncSession = Depends(get_db),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    course.is_published = False
    await db.commit()
    await db.refresh(course)
    return course


@router.delete("/{course_id}", response_model=MessageResponse)
async def delete_course(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("courses.delete")),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    course.deleted_at = datetime.now(timezone.utc)
    await record_audit_event(db, actor_id=user.id, action="course.delete", resource_type="course", resource_id=str(course_id))
    await db.commit()
    return MessageResponse(message="Course deleted.")


@router.post("/{course_id}/sections", response_model=SectionOut, status_code=201)
async def create_section(
    course_id: uuid.UUID,
    payload: SectionCreate,
    user: User = Depends(require_permission("lessons.manage", "courses.update")),
    db: AsyncSession = Depends(get_db),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    section = CourseSection(course_id=course_id, title=payload.title, order_index=payload.order_index)
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return SectionOut(id=section.id, title=section.title, order_index=section.order_index, lessons=[])


@router.post("/{course_id}/enroll", response_model=EnrollmentOut, status_code=201)
async def enroll(
    course_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    course = await db.get(Course, course_id)
    if course is None or not course.is_published:
        raise NotFoundError("Course not found.")

    existing = (await db.execute(
        select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.course_id == course_id)
    )).scalar_one_or_none()
    if existing:
        return EnrollmentOut(id=existing.id, course_id=course_id, status=existing.status, percent_complete=0)

    enrollment = Enrollment(student_id=user.id, course_id=course_id)
    db.add(enrollment)
    lessons_total = (await db.execute(
        select(Lesson).join(CourseSection).where(CourseSection.course_id == course_id)
    )).scalars().all()
    db.add(CourseProgress(student_id=user.id, course_id=course_id, lessons_total=len(lessons_total)))

    await record_audit_event(db, actor_id=user.id, action="course.enroll", resource_type="course", resource_id=str(course_id))
    await track_event(db, event_type="course_enrollment", user_id=user.id, metadata={"course_id": str(course_id)})
    await db.commit()

    await send_email(user.email, f"You're enrolled in {course.title}", "enrollment",
                      full_name=user.full_name, course_title=course.title,
                      course_url=f"/courses/{course.slug}")
    await emit_event("course.enrolled", {
        "email": user.email, "full_name": user.full_name,
        "course_title": course.title, "course_url": f"/courses/{course.slug}",
    })

    return EnrollmentOut(id=enrollment.id, course_id=course_id, status=enrollment.status, percent_complete=0)


@router.get("/me/enrollments", response_model=list[EnrollmentOut])
async def my_enrollments(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    enrollments = (await db.execute(select(Enrollment).where(Enrollment.student_id == user.id))).scalars().all()
    out = []
    for e in enrollments:
        progress = (await db.execute(
            select(CourseProgress).where(CourseProgress.student_id == user.id, CourseProgress.course_id == e.course_id)
        )).scalar_one_or_none()
        out.append(EnrollmentOut(id=e.id, course_id=e.course_id, status=e.status,
                                  percent_complete=progress.percent_complete if progress else 0))
    return out
