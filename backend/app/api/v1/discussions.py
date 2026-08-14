from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models.discussion import DiscussionReply, DiscussionThread, DiscussionVote
from app.models.lms import Course, Enrollment
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.discussion import ReplyCreate, ReplyOut, ThreadCreate, ThreadDetailOut, ThreadOut
from app.services.audit_service import record_audit_event

router = APIRouter(tags=["discussions"])


async def _get_course_or_404(db: AsyncSession, course_id: uuid.UUID) -> Course:
    course = await db.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise NotFoundError("Course not found.")
    return course


async def _can_read(course: Course, user: User | None) -> bool:
    """Published course discussions are open to anyone (matches how course
    content itself is browsable) — an unpublished course's discussions are
    only visible to its instructor or an admin, same access rule as the
    course draft itself (see courses.py's list_courses)."""
    if course.is_published:
        return True
    return user is not None and (user.id == course.instructor_id or user.has_permission("system.manage"))


async def _require_read_access(course: Course, user: User | None) -> None:
    if await _can_read(course, user):
        return
    if user is None:
        raise AuthenticationError("Sign in to view this course's discussions.")
    raise AuthorizationError("This course's discussions are only visible to its instructor or an admin.")


async def _can_post(db: AsyncSession, course: Course, user: User) -> bool:
    if user.id == course.instructor_id or user.has_permission("system.manage"):
        return True
    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.course_id == course.id)
    )).scalar_one_or_none()
    return enrolled is not None


async def _thread_out(db: AsyncSession, thread: DiscussionThread, viewer: User | None) -> ThreadOut:
    author = await db.get(User, thread.author_id) if thread.author_id else None
    reply_count = (await db.execute(
        select(func.count()).select_from(DiscussionReply).where(DiscussionReply.thread_id == thread.id)
    )).scalar_one()
    has_voted = False
    if viewer is not None:
        vote = (await db.execute(
            select(DiscussionVote).where(DiscussionVote.thread_id == thread.id, DiscussionVote.user_id == viewer.id)
        )).scalar_one_or_none()
        has_voted = vote is not None
    return ThreadOut(
        id=thread.id, course_id=thread.course_id, lesson_id=thread.lesson_id,
        author_id=thread.author_id, author_name=author.full_name if author else "Deleted user",
        title=thread.title, body=thread.body, is_resolved=thread.is_resolved,
        upvote_count=thread.upvote_count, reply_count=reply_count, created_at=thread.created_at,
        has_voted=has_voted,
    )


@router.post("/courses/{course_id}/discussions", response_model=ThreadOut, status_code=201)
async def create_thread(
    course_id: uuid.UUID,
    payload: ThreadCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    if not await _can_post(db, course, user):
        raise AuthorizationError("Enroll in this course to start a discussion.")
    thread = DiscussionThread(course_id=course_id, lesson_id=payload.lesson_id, author_id=user.id,
                               title=payload.title, body=payload.body)
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return await _thread_out(db, thread, user)


@router.get("/courses/{course_id}/discussions", response_model=list[ThreadOut])
async def list_threads(
    course_id: uuid.UUID,
    sort: str = Query("newest", pattern=r"^(newest|top)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    course = await _get_course_or_404(db, course_id)
    await _require_read_access(course, user)
    stmt = select(DiscussionThread).where(DiscussionThread.course_id == course_id)
    stmt = stmt.order_by(DiscussionThread.upvote_count.desc() if sort == "top" else DiscussionThread.created_at.desc())
    threads = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return [await _thread_out(db, t, user) for t in threads]


@router.get("/discussions/{thread_id}", response_model=ThreadDetailOut)
async def get_thread(
    thread_id: uuid.UUID,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise NotFoundError("Discussion thread not found.")
    course = await _get_course_or_404(db, thread.course_id)
    await _require_read_access(course, user)

    replies = (await db.execute(
        select(DiscussionReply).where(DiscussionReply.thread_id == thread_id).order_by(DiscussionReply.created_at.asc())
    )).scalars().all()
    reply_outs = []
    for r in replies:
        author = await db.get(User, r.author_id) if r.author_id else None
        reply_outs.append(ReplyOut(id=r.id, author_id=r.author_id, author_name=author.full_name if author else "Deleted user",
                                    body=r.body, is_instructor_answer=r.is_instructor_answer, created_at=r.created_at))

    base = await _thread_out(db, thread, user)
    return ThreadDetailOut(**base.model_dump(), replies=reply_outs)


@router.post("/discussions/{thread_id}/replies", response_model=ReplyOut, status_code=201)
async def create_reply(
    thread_id: uuid.UUID,
    payload: ReplyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise NotFoundError("Discussion thread not found.")
    course = await _get_course_or_404(db, thread.course_id)
    if not await _can_post(db, course, user):
        raise AuthorizationError("Enroll in this course to reply.")
    reply = DiscussionReply(thread_id=thread_id, author_id=user.id, body=payload.body,
                             is_instructor_answer=(user.id == course.instructor_id))
    db.add(reply)
    await db.commit()
    await db.refresh(reply)
    return ReplyOut(id=reply.id, author_id=reply.author_id, author_name=user.full_name,
                     body=reply.body, is_instructor_answer=reply.is_instructor_answer, created_at=reply.created_at)


@router.post("/discussions/{thread_id}/upvote", response_model=ThreadOut)
async def toggle_upvote(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise NotFoundError("Discussion thread not found.")
    course = await _get_course_or_404(db, thread.course_id)
    await _require_read_access(course, user)

    existing_vote = (await db.execute(
        select(DiscussionVote).where(DiscussionVote.thread_id == thread_id, DiscussionVote.user_id == user.id)
    )).scalar_one_or_none()
    if existing_vote is not None:
        await db.delete(existing_vote)
        thread.upvote_count = max(0, thread.upvote_count - 1)
    else:
        # Race-safe against a double-click firing two near-simultaneous
        # requests: the unique constraint on (thread_id, user_id) is the
        # real guard — if we lose the race, treat it the same as "already
        # voted" rather than surfacing a raw 500 (same SAVEPOINT pattern as
        # certificate_service.issue_certificate / gamification_service).
        try:
            async with db.begin_nested():
                db.add(DiscussionVote(thread_id=thread_id, user_id=user.id))
                await db.flush()
            thread.upvote_count += 1
        except IntegrityError:
            pass
    await db.commit()
    await db.refresh(thread)
    return await _thread_out(db, thread, user)


@router.post("/discussions/{thread_id}/resolve", response_model=ThreadOut)
async def resolve_thread(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise NotFoundError("Discussion thread not found.")
    course = await _get_course_or_404(db, thread.course_id)
    if user.id != course.instructor_id and not user.has_permission("system.manage"):
        raise AuthorizationError("Only the course instructor or an admin can resolve a thread.")
    thread.is_resolved = True
    await record_audit_event(db, actor_id=user.id, action="discussion.resolve", resource_type="discussion_thread", resource_id=str(thread_id))
    await db.commit()
    await db.refresh(thread)
    return await _thread_out(db, thread, user)


@router.delete("/discussions/{thread_id}", response_model=MessageResponse)
async def delete_thread(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.get(DiscussionThread, thread_id)
    if thread is None:
        raise NotFoundError("Discussion thread not found.")
    course = await _get_course_or_404(db, thread.course_id)
    if user.id != thread.author_id and user.id != course.instructor_id and not user.has_permission("system.manage"):
        raise AuthorizationError("You can only delete your own thread (or moderate as the course instructor/admin).")
    await db.delete(thread)
    await record_audit_event(db, actor_id=user.id, action="discussion.delete", resource_type="discussion_thread", resource_id=str(thread_id))
    await db.commit()
    return MessageResponse(message="Thread deleted.")
