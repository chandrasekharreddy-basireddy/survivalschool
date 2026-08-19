from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class Course(Base, UUIDPk, Timestamped):
    __tablename__ = "courses"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Indexed: the instructor dashboard and the exam flagged-attempts endpoint
    # both filter courses by instructor, which was a sequential scan.
    # Optional in the type too, matching nullable=True + ON DELETE SET NULL:
    # a GDPR-erased instructor leaves their courses ownerless, and every
    # ownership check must treat that as "nobody owns this" (only
    # system.manage can act on it) rather than trusting a non-null hint.
    instructor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prerequisite_course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL")
    )
    estimated_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Instructor-defined, shown on the course page and copied (snapshotted) onto
    # any certificate issued for this course at issuance time — see
    # certificate_service.issue_certificate(). Changing these later does not
    # retroactively change certificates already issued, which is intentional:
    # a certificate should reflect what was true when it was earned.
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    specialization: Mapped[str | None] = mapped_column(String(200))

    sections: Mapped[list[CourseSection]] = relationship(
        back_populates="course", order_by="CourseSection.order_index", cascade="all, delete-orphan"
    )


class CourseSection(Base, UUIDPk, Timestamped):
    __tablename__ = "course_sections"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    course: Mapped[Course] = relationship(back_populates="sections")
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="section", order_by="Lesson.order_index", cascade="all, delete-orphan"
    )


class Lesson(Base, UUIDPk, Timestamped):
    __tablename__ = "lessons"

    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_sections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), default="article", nullable=False)  # article|video|resource
    content_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    video_url: Mapped[str | None] = mapped_column(String(500))
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    section: Mapped[CourseSection] = relationship(back_populates="lessons")
    resources: Mapped[list[LessonResource]] = relationship(cascade="all, delete-orphan")


class LessonResource(Base, UUIDPk, Timestamped):
    __tablename__ = "lesson_resources"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id"))
    external_url: Mapped[str | None] = mapped_column(String(500))


class Enrollment(Base, UUIDPk, Timestamped):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|completed|dropped
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LessonProgress(Base, UUIDPk, Timestamped):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("student_id", "lesson_id", name="uq_progress_student_lesson"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_position_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CourseProgress(Base, UUIDPk, Timestamped):
    """Denormalized rollup, recalculated server-side whenever LessonProgress changes."""

    __tablename__ = "course_progress"
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_courseprogress_student_course"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    percent_complete: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lessons_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lessons_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
