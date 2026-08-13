from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.certificate import Certificate
from app.models.lms import Course
from app.models.user import User
from app.services.certificate_service import generate_qr_png_bytes, verification_url

router = APIRouter(prefix="/certificates", tags=["certificates"])


class CertificateOut(BaseModel):
    certificate_number: str
    course_title: str
    issued_at: str
    verify_url: str


class PublicCertificateOut(BaseModel):
    """Public verification endpoint — deliberately excludes email and any PII
    beyond first name (spec section 17: 'Do not expose unnecessary student
    information')."""
    valid: bool
    certificate_number: str | None = None
    course_title: str | None = None
    student_first_name: str | None = None
    issued_at: str | None = None


@router.get("/me", response_model=list[CertificateOut])
async def my_certificates(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Certificate).where(Certificate.student_id == user.id))).scalars().all()
    out = []
    for c in rows:
        course = await db.get(Course, c.course_id)
        out.append(CertificateOut(
            certificate_number=c.certificate_number, course_title=course.title if course else "",
            issued_at=c.issued_at.isoformat(), verify_url=verification_url(c.certificate_number),
        ))
    return out


@router.get("/verify/{certificate_number}", response_model=PublicCertificateOut)
async def verify_certificate(certificate_number: str, db: AsyncSession = Depends(get_db)):
    """Public endpoint — no auth required. Anyone with the certificate number
    (e.g. an employer, scanning the QR code) can confirm authenticity."""
    cert = (await db.execute(select(Certificate).where(Certificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None or cert.revoked_at is not None:
        return PublicCertificateOut(valid=False)
    course = await db.get(Course, cert.course_id)
    student = await db.get(User, cert.student_id)
    return PublicCertificateOut(
        valid=True, certificate_number=cert.certificate_number,
        course_title=course.title if course else None,
        student_first_name=(student.full_name.split(" ")[0] if student else None),
        issued_at=cert.issued_at.isoformat(),
    )


@router.get("/{certificate_number}/qr")
async def certificate_qr(certificate_number: str, db: AsyncSession = Depends(get_db)):
    cert = (await db.execute(select(Certificate).where(Certificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None:
        raise NotFoundError("Certificate not found.")
    png_bytes = generate_qr_png_bytes(cert.certificate_number)
    return Response(content=png_bytes, media_type="image/png")
