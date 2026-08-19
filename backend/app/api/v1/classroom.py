from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationAppError,
)
from app.database import get_db
from app.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_course_ownership,
    require_permission,
)
from app.models.classroom import (
    Announcement,
    AnnouncementComment,
    Assignment,
    AssignmentComment,
    AssignmentSubmission,
)
from app.models.lms import Course, Enrollment
from app.models.user import User
from app.schemas.classroom import (
    AnnouncementCommentCreate,
    AnnouncementCommentOut,
    AnnouncementCreate,
    AnnouncementOut,
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    GradebookOut,
    GradebookRowOut,
    GradeIn,
    RosterMemberOut,
    SubmissionCommentCreate,
    SubmissionCommentOut,
    SubmissionOut,
    SubmissionSubmit,
)
from app.services.audit_service import record_audit_event
from app.services.notification_service import create_notification

router = APIRouter(prefix="/courses/{course_id}", tags=["classroom"])


async def _get_course_or_404(db: AsyncSession, course_id: uuid.UUID) -> Course:
    course = await db.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise NotFoundError("Course not found.")
    return course


def _is_staff(course: Course, user: User | None) -> bool:
    return user is not None and (user.id == course.instructor_id or user.has_permission("system.manage"))


async def _is_enrolled(db: AsyncSession, course_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = (await db.execute(
        select(Enrollment).where(Enrollment.student_id == user_id, Enrollment.course_id == course_id, Enrollment.status == "active")
    )).scalar_one_or_none()
    return row is not None


async def _require_class_member(db: AsyncSession, course: Course, user: User | None) -> None:
    """Classroom content is class-private, not course-public like discussions
    — only that course's instructor/admin or an actively enrolled student
    may see the stream, classwork, roster, or grades."""
    if user is None:
        raise AuthenticationError("Sign in to view this class.")
    if _is_staff(course, user):
        return
    if await _is_enrolled(db, course.id, user.id):
        return
    raise AuthorizationError("You're not a member of this class.")


async def _enrolled_students(db: AsyncSession, course_id: uuid.UUID) -> list[User]:
    return list((await db.execute(
        select(User).join(Enrollment, Enrollment.student_id == User.id)
        .where(Enrollment.course_id == course_id, Enrollment.status == "active")
        .order_by(User.full_name)
    )).scalars().all())


# ---- People ----

@router.get("/people", response_model=list[RosterMemberOut])
async def get_roster(
    course_id: uuid.UUID,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    await _require_class_member(db, course, user)

    members: list[RosterMemberOut] = []
    if course.instructor_id:
        instructor = await db.get(User, course.instructor_id)
        if instructor:
            members.append(RosterMemberOut(user_id=instructor.id, full_name=instructor.full_name, email=instructor.email, role="instructor"))
    for student in await _enrolled_students(db, course_id):
        members.append(RosterMemberOut(user_id=student.id, full_name=student.full_name, email=student.email, role="student"))
    return members


# ---- Stream ----

async def _announcement_out(db: AsyncSession, a: Announcement) -> AnnouncementOut:
    author = await db.get(User, a.author_id) if a.author_id else None
    count = (await db.execute(select(func.count()).select_from(AnnouncementComment).where(AnnouncementComment.announcement_id == a.id))).scalar_one()
    return AnnouncementOut(
        id=a.id, course_id=a.course_id, author_id=a.author_id, author_name=author.full_name if author else "Unknown",
        body=a.body, is_pinned=a.is_pinned, comment_count=count, created_at=a.created_at,
    )


@router.get("/stream", response_model=list[AnnouncementOut])
async def list_announcements(
    course_id: uuid.UUID,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    await _require_class_member(db, course, user)
    rows = (await db.execute(
        select(Announcement).where(Announcement.course_id == course_id)
        .order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
    )).scalars().all()
    return [await _announcement_out(db, a) for a in rows]


@router.post("/stream", response_model=AnnouncementOut, status_code=201)
async def post_announcement(
    course_id: uuid.UUID,
    payload: AnnouncementCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_permission("lessons.manage")),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_ownership(db, user, course_id)
    announcement = Announcement(course_id=course.id, author_id=user.id, body=payload.body, is_pinned=payload.is_pinned)
    db.add(announcement)
    await record_audit_event(db, actor_id=user.id, action="classroom.announcement_posted", resource_type="course", resource_id=str(course_id))
    await db.commit()
    await db.refresh(announcement)

    for student in await _enrolled_students(db, course_id):
        background_tasks.add_task(
            _notify_student_of_announcement, student.id, course.title, course.slug, payload.body[:200]
        )
    return await _announcement_out(db, announcement)


async def _notify_student_of_announcement(student_id: uuid.UUID, course_title: str, course_slug: str, preview: str) -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as bg_db:
        student = await bg_db.get(User, student_id)
        if student is None:
            return
        await create_notification(
            bg_db, user=student, category="announcement", title=f"New announcement in {course_title}",
            body=preview, link_url=f"/courses/{course_slug}",
        )
        await bg_db.commit()


@router.delete("/stream/{announcement_id}")
async def delete_announcement(
    course_id: uuid.UUID,
    announcement_id: uuid.UUID,
    user: User = Depends(require_permission("lessons.manage")),
    db: AsyncSession = Depends(get_db),
):
    await require_course_ownership(db, user, course_id)
    announcement = await db.get(Announcement, announcement_id)
    if announcement is None or announcement.course_id != course_id:
        raise NotFoundError("Announcement not found.")
    await db.delete(announcement)
    await db.commit()
    return {"message": "Announcement deleted."}


@router.get("/stream/{announcement_id}/comments", response_model=list[AnnouncementCommentOut])
async def list_announcement_comments(
    course_id: uuid.UUID,
    announcement_id: uuid.UUID,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    await _require_class_member(db, course, user)
    announcement = await db.get(Announcement, announcement_id)
    if announcement is None or announcement.course_id != course_id:
        raise NotFoundError("Announcement not found.")
    rows = (await db.execute(
        select(AnnouncementComment).where(AnnouncementComment.announcement_id == announcement_id).order_by(AnnouncementComment.created_at)
    )).scalars().all()
    out = []
    for c in rows:
        author = await db.get(User, c.author_id) if c.author_id else None
        out.append(AnnouncementCommentOut(id=c.id, announcement_id=c.announcement_id, author_id=c.author_id,
                                           author_name=author.full_name if author else "Unknown", body=c.body, created_at=c.created_at))
    return out


@router.post("/stream/{announcement_id}/comments", response_model=AnnouncementCommentOut, status_code=201)
async def post_announcement_comment(
    course_id: uuid.UUID,
    announcement_id: uuid.UUID,
    payload: AnnouncementCommentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    await _require_class_member(db, course, user)
    announcement = await db.get(Announcement, announcement_id)
    if announcement is None or announcement.course_id != course_id:
        raise NotFoundError("Announcement not found.")
    comment = AnnouncementComment(announcement_id=announcement_id, author_id=user.id, body=payload.body)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return AnnouncementCommentOut(id=comment.id, announcement_id=comment.announcement_id, author_id=user.id,
                                   author_name=user.full_name, body=comment.body, created_at=comment.created_at)


# ---- Classwork ----

async def _assignment_out(db: AsyncSession, a: Assignment, viewer: User | None) -> AssignmentOut:
    my_status = None
    my_grade = None
    if viewer and not _is_staff_for_assignment(a, viewer):
        sub = (await db.execute(
            select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == a.id, AssignmentSubmission.student_id == viewer.id)
        )).scalar_one_or_none()
        my_status = sub.status if sub else "not_submitted"
        my_grade = sub.grade if sub else None
    return AssignmentOut(
        id=a.id, course_id=a.course_id, title=a.title, instructions=a.instructions, due_at=a.due_at,
        points_possible=a.points_possible, is_published=a.is_published, attachments=a.attachments,
        created_at=a.created_at, my_status=my_status, my_grade=my_grade,
    )


def _is_staff_for_assignment(a: Assignment, viewer: User) -> bool:
    return viewer.id == a.created_by or viewer.has_permission("system.manage")


@router.get("/classwork", response_model=list[AssignmentOut])
async def list_classwork(
    course_id: uuid.UUID,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    await _require_class_member(db, course, user)
    stmt = select(Assignment).where(Assignment.course_id == course_id)
    if not _is_staff(course, user):
        stmt = stmt.where(Assignment.is_published.is_(True))
    rows = (await db.execute(stmt.order_by(Assignment.due_at.is_(None), Assignment.due_at, Assignment.created_at.desc()))).scalars().all()
    return [await _assignment_out(db, a, user) for a in rows]


@router.post("/classwork", response_model=AssignmentOut, status_code=201)
async def create_classwork(
    course_id: uuid.UUID,
    payload: AssignmentCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_permission("lessons.manage")),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_ownership(db, user, course_id)
    assignment = Assignment(
        course_id=course.id, created_by=user.id, title=payload.title, instructions=payload.instructions,
        due_at=payload.due_at, points_possible=payload.points_possible, is_published=payload.is_published,
        attachments=[a.model_dump(mode="json") for a in payload.attachments],
    )
    db.add(assignment)
    await record_audit_event(db, actor_id=user.id, action="classroom.assignment_created", resource_type="course", resource_id=str(course_id))
    await db.commit()
    await db.refresh(assignment)

    if payload.is_published:
        for student in await _enrolled_students(db, course_id):
            background_tasks.add_task(_notify_student_of_new_assignment, student.id, course.title, assignment.title)
    return await _assignment_out(db, assignment, user)


async def _notify_student_of_new_assignment(student_id: uuid.UUID, course_title: str, assignment_title: str) -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as bg_db:
        student = await bg_db.get(User, student_id)
        if student is None:
            return
        await create_notification(
            bg_db, user=student, category="course", title=f"New assignment: {assignment_title}",
            body=f"Posted in {course_title}.",
        )
        await bg_db.commit()


@router.patch("/classwork/{assignment_id}", response_model=AssignmentOut)
async def update_classwork(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: AssignmentUpdate,
    user: User = Depends(require_permission("lessons.manage")),
    db: AsyncSession = Depends(get_db),
):
    await require_course_ownership(db, user, course_id)
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id:
        raise NotFoundError("Assignment not found.")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(assignment, field, value)
    await db.commit()
    await db.refresh(assignment)
    return await _assignment_out(db, assignment, user)


@router.delete("/classwork/{assignment_id}")
async def delete_classwork(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    user: User = Depends(require_permission("lessons.manage")),
    db: AsyncSession = Depends(get_db),
):
    await require_course_ownership(db, user, course_id)
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id:
        raise NotFoundError("Assignment not found.")
    await db.delete(assignment)
    await db.commit()
    return {"message": "Assignment deleted."}


async def _get_or_create_submission(db: AsyncSession, assignment_id: uuid.UUID, student_id: uuid.UUID) -> AssignmentSubmission:
    sub = (await db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == assignment_id, AssignmentSubmission.student_id == student_id)
    )).scalar_one_or_none()
    if sub is None:
        sub = AssignmentSubmission(assignment_id=assignment_id, student_id=student_id)
        db.add(sub)
        await db.flush()
    return sub


def _submission_out(sub: AssignmentSubmission, student_name: str) -> SubmissionOut:
    return SubmissionOut(
        id=sub.id, assignment_id=sub.assignment_id, student_id=sub.student_id, student_name=student_name,
        content=sub.content, attachments=sub.attachments, status=sub.status, submitted_at=sub.submitted_at,
        grade=sub.grade, feedback=sub.feedback, graded_at=sub.graded_at,
    )


@router.post("/classwork/{assignment_id}/submit", response_model=SubmissionOut)
async def submit_classwork(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: SubmissionSubmit,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_course_or_404(db, course_id)
    if not await _is_enrolled(db, course_id, user.id):
        raise AuthorizationError("You're not enrolled in this course.")
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id or not assignment.is_published:
        raise NotFoundError("Assignment not found.")

    sub = await _get_or_create_submission(db, assignment_id, user.id)
    sub.content = payload.content
    sub.attachments = [a.model_dump(mode="json") for a in payload.attachments]
    sub.status = "submitted"
    sub.submitted_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(sub)

    if assignment.created_by:
        background_tasks.add_task(_notify_instructor_of_submission, assignment.created_by, user.full_name, assignment.title)
    return _submission_out(sub, user.full_name)


async def _notify_instructor_of_submission(instructor_id: uuid.UUID, student_name: str, assignment_title: str) -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as bg_db:
        instructor = await bg_db.get(User, instructor_id)
        if instructor is None:
            return
        await create_notification(
            bg_db, user=instructor, category="course", title=f"{student_name} submitted {assignment_title}",
        )
        await bg_db.commit()


@router.get("/classwork/{assignment_id}/submissions/me", response_model=SubmissionOut)
async def my_submission(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id:
        raise NotFoundError("Assignment not found.")
    sub = await _get_or_create_submission(db, assignment_id, user.id)
    await db.commit()
    return _submission_out(sub, user.full_name)


@router.get("/classwork/{assignment_id}/submissions", response_model=list[SubmissionOut])
async def list_submissions(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    user: User = Depends(require_permission("lessons.manage")),
    db: AsyncSession = Depends(get_db),
):
    await require_course_ownership(db, user, course_id)
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id:
        raise NotFoundError("Assignment not found.")
    rows = (await db.execute(
        select(AssignmentSubmission, User.full_name)
        .join(User, User.id == AssignmentSubmission.student_id)
        .where(AssignmentSubmission.assignment_id == assignment_id)
    )).all()
    return [_submission_out(sub, name) for sub, name in rows]


@router.post("/classwork/{assignment_id}/submissions/{submission_id}/grade", response_model=SubmissionOut)
async def grade_submission(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    submission_id: uuid.UUID,
    payload: GradeIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_permission("lessons.manage")),
    db: AsyncSession = Depends(get_db),
):
    await require_course_ownership(db, user, course_id)
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id:
        raise NotFoundError("Assignment not found.")
    if payload.grade > assignment.points_possible:
        raise ValidationAppError(f"Grade can't exceed {assignment.points_possible} points.")
    sub = await db.get(AssignmentSubmission, submission_id)
    if sub is None or sub.assignment_id != assignment_id:
        raise NotFoundError("Submission not found.")

    sub.grade = payload.grade
    sub.feedback = payload.feedback
    sub.status = "graded"
    sub.graded_by = user.id
    sub.graded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(sub)

    student = await db.get(User, sub.student_id)
    background_tasks.add_task(_notify_student_of_grade, sub.student_id, assignment.title, payload.grade, assignment.points_possible)
    return _submission_out(sub, student.full_name if student else "")


async def _notify_student_of_grade(student_id: uuid.UUID, assignment_title: str, grade: int, points_possible: int) -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as bg_db:
        student = await bg_db.get(User, student_id)
        if student is None:
            return
        await create_notification(
            bg_db, user=student, category="assessment", title=f"Graded: {assignment_title}",
            body=f"{grade}/{points_possible}",
        )
        await bg_db.commit()


@router.get("/classwork/{assignment_id}/submissions/{submission_id}/comments", response_model=list[SubmissionCommentOut])
async def list_submission_comments(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    submission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    sub = await db.get(AssignmentSubmission, submission_id)
    if sub is None or sub.assignment_id != assignment_id:
        raise NotFoundError("Submission not found.")
    if not (sub.student_id == user.id or _is_staff(course, user)):
        raise AuthorizationError("You can't view this submission's comments.")
    rows = (await db.execute(
        select(AssignmentComment).where(AssignmentComment.submission_id == submission_id).order_by(AssignmentComment.created_at)
    )).scalars().all()
    out = []
    for c in rows:
        author = await db.get(User, c.author_id) if c.author_id else None
        out.append(SubmissionCommentOut(id=c.id, submission_id=c.submission_id, author_id=c.author_id,
                                         author_name=author.full_name if author else "Unknown", body=c.body, created_at=c.created_at))
    return out


@router.post("/classwork/{assignment_id}/submissions/{submission_id}/comments", response_model=SubmissionCommentOut, status_code=201)
async def post_submission_comment(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    submission_id: uuid.UUID,
    payload: SubmissionCommentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    sub = await db.get(AssignmentSubmission, submission_id)
    if sub is None or sub.assignment_id != assignment_id:
        raise NotFoundError("Submission not found.")
    if not (sub.student_id == user.id or _is_staff(course, user)):
        raise AuthorizationError("You can't comment on this submission.")
    comment = AssignmentComment(submission_id=submission_id, author_id=user.id, body=payload.body)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return SubmissionCommentOut(id=comment.id, submission_id=comment.submission_id, author_id=user.id,
                                 author_name=user.full_name, body=comment.body, created_at=comment.created_at)


# ---- Grades ----

@router.get("/grades", response_model=GradebookOut)
async def get_gradebook(
    course_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    await _require_class_member(db, course, user)
    is_staff = _is_staff(course, user)

    assignments = (await db.execute(
        select(Assignment).where(Assignment.course_id == course_id, Assignment.is_published.is_(True)).order_by(Assignment.created_at)
    )).scalars().all()
    assignment_outs = [await _assignment_out(db, a, user) for a in assignments]
    assignment_ids = [a.id for a in assignments]

    students = [user] if not is_staff else await _enrolled_students(db, course_id)
    if not is_staff and not await _is_enrolled(db, course_id, user.id):
        raise AuthorizationError("You're not enrolled in this course.")

    rows: list[GradebookRowOut] = []
    for student in students:
        subs = {}
        if assignment_ids:
            subs = {
                s.assignment_id: s.grade
                for s in (await db.execute(
                    select(AssignmentSubmission).where(AssignmentSubmission.assignment_id.in_(assignment_ids), AssignmentSubmission.student_id == student.id)
                )).scalars().all()
            }
        grades = {str(a.id): subs.get(a.id) for a in assignments}
        earned = sum(g for g in grades.values() if g is not None)
        possible = sum(a.points_possible for a in assignments if grades[str(a.id)] is not None)
        rows.append(GradebookRowOut(student_id=student.id, student_name=student.full_name, grades=grades, total_earned=earned, total_possible=possible))

    return GradebookOut(assignments=assignment_outs, rows=rows)
