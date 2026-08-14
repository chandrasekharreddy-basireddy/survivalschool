from __future__ import annotations

import io
import secrets

import qrcode
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.certificate import Certificate
from app.models.lms import Course
from app.models.user import User

settings = get_settings()


def _generate_certificate_number() -> str:
    return f"SS-{secrets.token_hex(6).upper()}"


async def issue_certificate(db: AsyncSession, student: User, course: Course) -> Certificate:
    existing = (await db.execute(
        select(Certificate).where(Certificate.student_id == student.id, Certificate.course_id == course.id)
    )).scalar_one_or_none()
    if existing:
        return existing

    cert = Certificate(certificate_number=_generate_certificate_number(), student_id=student.id, course_id=course.id)
    try:
        async with db.begin_nested():
            db.add(cert)
            await db.flush()
    except IntegrityError:
        # Lost a race with a concurrent request completing the same course for
        # the same student (e.g. two tabs finishing the last lesson at once).
        # The unique constraint on (student_id, course_id) already prevented a
        # duplicate certificate — re-select the one the other request created
        # instead of surfacing a 500 for what is, from the student's
        # perspective, a completely normal course completion.
        existing = (await db.execute(
            select(Certificate).where(Certificate.student_id == student.id, Certificate.course_id == course.id)
        )).scalar_one()
        return existing
    return cert


def verification_url(certificate_number: str) -> str:
    return f"{settings.FRONTEND_URL}/verify/certificate/{certificate_number}"


def generate_qr_png_bytes(certificate_number: str) -> bytes:
    img = qrcode.make(verification_url(certificate_number))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
