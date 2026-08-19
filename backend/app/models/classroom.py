from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk

# ---- Native "Classroom" features: Stream, Classwork, People, Grades ----
#
# Built entirely on this platform's own Course/Enrollment — no Google account
# or OAuth involved. Deliberately class-scoped-private (unlike
# DiscussionThread, which is readable by anyone once a course is published):
# an assignment, its due date, and a student's grade are visible only to that
# course's instructor and its enrolled students, matching real Google
# Classroom's own privacy model. "People" (the roster) needs no new table —
# it's just Course.instructor_id + Enrollment — so only Stream and Classwork
# get models here.


class Announcement(Base, UUIDPk, Timestamped):
    __tablename__ = "announcements"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AnnouncementComment(Base, UUIDPk, Timestamped):
    __tablename__ = "announcement_comments"

    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Assignment(Base, UUIDPk, Timestamped):
    __tablename__ = "assignments"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    points_possible: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # [{"file_id": "...", "title": "..."}] — file_id points at an existing
    # FileObject uploaded via POST /files, never stored inline here.
    attachments: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)


class AssignmentSubmission(Base, UUIDPk, Timestamped):
    """Created lazily (get-or-create) the first time a student submits or
    comments on an assignment — a row always exists once there's anything to
    say about it, but browsing the assignment list itself doesn't create one
    for every enrolled student up front."""

    __tablename__ = "assignment_submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),)

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attachments: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="not_submitted", nullable=False)  # not_submitted|submitted|graded|returned
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grade: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)
    graded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssignmentComment(Base, UUIDPk, Timestamped):
    """Private, per-student thread on a submission — visible only to that
    student and the instructor, same as Google Classroom's private comments."""

    __tablename__ = "assignment_comments"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignment_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
