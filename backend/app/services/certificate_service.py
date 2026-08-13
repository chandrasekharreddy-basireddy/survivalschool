from __future__ import annotations

import io
import secrets

import qrcode
from sqlalchemy import select
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
    db.add(cert)
    await db.flush()
    return cert


def verification_url(certificate_number: str) -> str:
    return f"{settings.FRONTEND_URL}/verify/certificate/{certificate_number}"


def generate_qr_png_bytes(certificate_number: str) -> bytes:
    img = qrcode.make(verification_url(certificate_number))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
