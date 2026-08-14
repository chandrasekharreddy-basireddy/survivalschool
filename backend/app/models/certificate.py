from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class Certificate(Base, UUIDPk, Timestamped):
    __tablename__ = "certificates"
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_certificate_student_course"),)

    certificate_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id"))

    # Snapshotted at issuance by certificate_service.issue_certificate() —
    # these deliberately copy data from Course/User at the moment the
    # certificate is earned rather than joining live, so a certificate's
    # displayed content never silently changes after the fact (e.g. if the
    # instructor is later reassigned or the course's skill list edited).
    grade: Mapped[str | None] = mapped_column(String(10))
    score_percent: Mapped[int | None] = mapped_column(Integer)
    skills_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    specialization: Mapped[str | None] = mapped_column(String(200))
    instructor_name: Mapped[str | None] = mapped_column(String(150))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
