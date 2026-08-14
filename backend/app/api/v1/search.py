from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.discussion import DiscussionThread
from app.models.lms import Course
from app.schemas.search import SearchResponse, SearchResultOut

router = APIRouter(prefix="/search", tags=["search"])


def _snippet(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Public, unauthenticated search. Deliberately scoped to PUBLISHED
    course content only, on both sides of the query: courses must be
    published, and discussion threads are only searched on courses that are
    published — a private/unpublished course's discussions never leak
    through search, matching the same access rule enforced directly on
    those endpoints (see discussions.py's _can_read)."""
    like = f"%{q}%"
    per_type_limit = max(1, limit // 2)

    course_rows = (await db.execute(
        select(Course)
        .where(Course.is_published.is_(True), Course.deleted_at.is_(None))
        .where(or_(Course.title.ilike(like), Course.description.ilike(like)))
        .order_by(Course.created_at.desc())
        .limit(per_type_limit)
    )).scalars().all()

    thread_rows = (await db.execute(
        select(DiscussionThread, Course)
        .join(Course, Course.id == DiscussionThread.course_id)
        .where(Course.is_published.is_(True))
        .where(or_(DiscussionThread.title.ilike(like), DiscussionThread.body.ilike(like)))
        .order_by(DiscussionThread.created_at.desc())
        .limit(limit - min(len(course_rows), per_type_limit))
    )).all()

    results: list[SearchResultOut] = []
    for c in course_rows:
        results.append(SearchResultOut(type="course", id=c.id, title=c.title, snippet=_snippet(c.description),
                                        course_id=c.id, course_slug=c.slug))
    for thread, course in thread_rows:
        results.append(SearchResultOut(type="discussion", id=thread.id, title=thread.title, snippet=_snippet(thread.body),
                                        course_id=course.id, course_slug=course.slug))

    return SearchResponse(query=q, results=results[:limit])
