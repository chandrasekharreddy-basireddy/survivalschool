from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthenticationError, AuthorizationError, ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import (
    get_current_user,
    get_current_user_optional,
    get_current_verified_user,
    require_course_ownership,
    require_permission,
)
from app.models.assessment import Exam, ExamAnswer, ExamAttempt, Question, Quiz, QuizAnswer, QuizAttempt
from app.models.lms import Course, CourseProgress, CourseSection, Enrollment, Lesson
from app.models.user import User
from app.schemas.analytics_extra import CourseAnalyticsOverviewOut, QuestionAnalyticsOut
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
from app.services.cache_service import bump_cache_version, cache_get_versioned, cache_set_versioned
from app.services.email_service import send_email
from app.services.n8n_service import emit_event

router = APIRouter(prefix="/courses", tags=["courses"])

# Short TTL: this is a cache for the public catalog's read-heavy traffic,
# not a source of truth — a 30s staleness window on a course list is
# invisible to a normal browsing user, and every write path below bumps the
# version immediately so it self-corrects the moment anything changes.
_COURSES_LIST_TTL = 30


async def _require_analytics_access(db: AsyncSession, user: User, course_id: uuid.UUID) -> Course:
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    if course.instructor_id != user.id and not user.has_permission("system.manage"):
        raise AuthorizationError("You can only view analytics for your own courses.")
    return course


async def _question_analytics(db: AsyncSession, course_id: uuid.UUID) -> list[QuestionAnalyticsOut]:
    quiz_ids = (await db.execute(select(Quiz.id).where(Quiz.course_id == course_id))).scalars().all()
    exam_ids = (await db.execute(select(Exam.id).where(Exam.course_id == course_id))).scalars().all()

    stats: dict[uuid.UUID, dict[str, int]] = {}
    if quiz_ids:
        rows = (await db.execute(
            select(QuizAnswer.question_id, QuizAnswer.is_correct)
            .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
            .where(QuizAttempt.quiz_id.in_(quiz_ids), QuizAttempt.status == "submitted")
        )).all()
        for qid, is_correct in rows:
            s = stats.setdefault(qid, {"answered": 0, "correct": 0})
            s["answered"] += 1
            s["correct"] += 1 if is_correct else 0
    if exam_ids:
        rows = (await db.execute(
            select(ExamAnswer.question_id, ExamAnswer.is_correct)
            .join(ExamAttempt, ExamAttempt.id == ExamAnswer.attempt_id)
            .where(ExamAttempt.exam_id.in_(exam_ids), ExamAttempt.status == "submitted")
        )).all()
        for qid, is_correct in rows:
            s = stats.setdefault(qid, {"answered": 0, "correct": 0})
            s["answered"] += 1
            s["correct"] += 1 if is_correct else 0

    if not stats:
        return []
    questions = (await db.execute(select(Question).where(Question.id.in_(stats.keys())))).scalars().all()
    out = []
    for q in questions:
        s = stats[q.id]
        pct = round((s["correct"] / s["answered"]) * 100, 1) if s["answered"] else 0.0
        out.append(QuestionAnalyticsOut(question_id=q.id, prompt=q.prompt, question_type=q.question_type,
                                         times_answered=s["answered"], times_correct=s["correct"], percent_correct=pct))
    return sorted(out, key=lambda x: x.percent_correct)


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
    # Only cache the public catalog (published_only=True, the overwhelmingly
    # common case — anonymous browsing and the course list page). The
    # published_only=False branch below returns caller-specific results
    # (an instructor's own drafts, or an admin's everything) that would be
    # unsafe to cache under a shared key, so it always hits Postgres.
    cache_key = f"search={search or ''}:limit={limit}:offset={offset}"
    if published_only:
        cached = await cache_get_versioned("courses_list", cache_key)
        if cached is not None:
            response.headers["X-Total-Count"] = str(cached["total"])
            return cached["courses"]

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
    courses = result.scalars().all()
    if published_only:
        payload = {"total": total, "courses": [CourseOut.model_validate(c).model_dump(mode="json") for c in courses]}
        await cache_set_versioned("courses_list", cache_key, payload, _COURSES_LIST_TTL)
    return courses


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
    await bump_cache_version("courses_list")
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
    course = await require_course_ownership(db, user, course_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    await record_audit_event(db, actor_id=user.id, action="course.update", resource_type="course", resource_id=str(course_id))
    await db.commit()
    await db.refresh(course)
    await bump_cache_version("courses_list")
    return course


@router.post("/{course_id}/publish", response_model=CourseOut)
async def publish_course(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("courses.update")),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_ownership(db, user, course_id)
    course.is_published = True
    await record_audit_event(db, actor_id=user.id, action="course.publish", resource_type="course", resource_id=str(course_id))
    await db.commit()
    await db.refresh(course)
    await bump_cache_version("courses_list")
    return course


@router.post("/{course_id}/unpublish", response_model=CourseOut)
async def unpublish_course(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("courses.update")),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_ownership(db, user, course_id)
    course.is_published = False
    await db.commit()
    await db.refresh(course)
    await bump_cache_version("courses_list")
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
    await bump_cache_version("courses_list")
    return MessageResponse(message="Course deleted.")


@router.post("/{course_id}/sections", response_model=SectionOut, status_code=201)
async def create_section(
    course_id: uuid.UUID,
    payload: SectionCreate,
    user: User = Depends(require_permission("lessons.manage", "courses.update")),
    db: AsyncSession = Depends(get_db),
):
    # lessons.manage/courses.update are granted to every INSTRUCTOR — without
    # this, any instructor could add sections to any other instructor's course.
    await require_course_ownership(db, user, course_id)
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


@router.get("/{course_id}/analytics/overview", response_model=CourseAnalyticsOverviewOut)
async def course_analytics_overview(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("results.view")),
    db: AsyncSession = Depends(get_db),
):
    await _require_analytics_access(db, user, course_id)

    enrolled_count = (await db.execute(
        select(func.count()).select_from(Enrollment).where(Enrollment.course_id == course_id)
    )).scalar_one()
    completed_count = (await db.execute(
        select(func.count()).select_from(Enrollment).where(Enrollment.course_id == course_id, Enrollment.status == "completed")
    )).scalar_one()

    quiz_ids = (await db.execute(select(Quiz.id).where(Quiz.course_id == course_id))).scalars().all()
    exam_ids = (await db.execute(select(Exam.id).where(Exam.course_id == course_id))).scalars().all()

    quiz_scores: list[int] = []
    if quiz_ids:
        quiz_scores = list((await db.execute(
            select(QuizAttempt.score_percent).where(QuizAttempt.quiz_id.in_(quiz_ids), QuizAttempt.status == "submitted", QuizAttempt.score_percent.is_not(None))
        )).scalars().all())
    exam_scores: list[int] = []
    if exam_ids:
        exam_scores = list((await db.execute(
            select(ExamAttempt.score_percent).where(ExamAttempt.exam_id.in_(exam_ids), ExamAttempt.status == "submitted", ExamAttempt.score_percent.is_not(None))
        )).scalars().all())

    all_scores = quiz_scores + exam_scores
    buckets = {"0-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
    for s in all_scores:
        if s < 60:
            buckets["0-59"] += 1
        elif s < 70:
            buckets["60-69"] += 1
        elif s < 80:
            buckets["70-79"] += 1
        elif s < 90:
            buckets["80-89"] += 1
        else:
            buckets["90-100"] += 1

    return CourseAnalyticsOverviewOut(
        course_id=course_id, enrolled_count=enrolled_count, completed_count=completed_count,
        completion_rate_percent=round((completed_count / enrolled_count) * 100, 1) if enrolled_count else 0.0,
        quiz_attempts_count=len(quiz_scores), exam_attempts_count=len(exam_scores),
        average_quiz_score_percent=round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else None,
        average_exam_score_percent=round(sum(exam_scores) / len(exam_scores), 1) if exam_scores else None,
        score_distribution=buckets,
    )


@router.get("/{course_id}/analytics/questions", response_model=list[QuestionAnalyticsOut])
async def course_analytics_questions(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("results.view")),
    db: AsyncSession = Depends(get_db),
):
    await _require_analytics_access(db, user, course_id)
    return await _question_analytics(db, course_id)


@router.get("/{course_id}/analytics/export.csv")
async def course_analytics_export_csv(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("results.view")),
    db: AsyncSession = Depends(get_db),
):
    course = await _require_analytics_access(db, user, course_id)
    rows = await _question_analytics(db, course_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["question_id", "prompt", "question_type", "times_answered", "times_correct", "percent_correct"])
    for r in rows:
        writer.writerow([str(r.question_id), r.prompt, r.question_type, r.times_answered, r.times_correct, r.percent_correct])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={course.slug}-question-analytics.csv"},
    )
