from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.certificate import Certificate
from app.models.lms import Course
from app.models.user import User
from app.services.audit_service import record_audit_event
from app.services.certificate_service import (
    generate_certificate_pdf_bytes,
    generate_qr_png_bytes,
    verification_url,
)

router = APIRouter(prefix="/certificates", tags=["certificates"])


class CertificateOut(BaseModel):
    certificate_number: str
    course_title: str
    issued_at: str
    verify_url: str
    grade: str | None = None
    score_percent: int | None = None
    skills: list[str] = []
    specialization: str | None = None
    instructor_name: str | None = None
    expires_at: str | None = None
    revoked: bool = False


class PublicCertificateOut(BaseModel):
    """Public verification endpoint — deliberately excludes email and any PII
    beyond the student's name (spec section 17: 'Do not expose unnecessary
    student information'; full name is shown, not just first name, because
    the certificate itself is meant to be shown to employers)."""
    valid: bool
    certificate_number: str | None = None
    course_title: str | None = None
    student_full_name: str | None = None
    grade: str | None = None
    score_percent: int | None = None
    skills: list[str] = []
    specialization: str | None = None
    instructor_name: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    verify_url: str | None = None
    invalid_reason: str | None = None


class RevokeCertificateOut(BaseModel):
    certificate_number: str
    revoked_at: str


def _is_expired(cert: Certificate) -> bool:
    return cert.expires_at is not None and cert.expires_at < datetime.now(UTC)


@router.get("/me", response_model=list[CertificateOut])
async def my_certificates(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Single joined query instead of one db.get(Course, ...) per certificate —
    # avoids the N+1 the production audit flagged on this endpoint.
    # Outer join: a certificate whose course was later deleted (course_id is
    # SET NULL) must still appear in the holder's list — it falls back to the
    # course_title snapshotted at issuance.
    rows = (await db.execute(
        select(Certificate, Course)
        .outerjoin(Course, Course.id == Certificate.course_id)
        .where(Certificate.student_id == user.id)
    )).all()
    return [
        CertificateOut(
            certificate_number=c.certificate_number,
            course_title=(course.title if course else c.course_title) or "Course",
            issued_at=c.issued_at.isoformat(), verify_url=verification_url(c.certificate_number),
            grade=c.grade, score_percent=c.score_percent, skills=list(c.skills_json or []),
            specialization=c.specialization, instructor_name=c.instructor_name,
            expires_at=c.expires_at.isoformat() if c.expires_at else None,
            revoked=c.revoked_at is not None,
        )
        for c, course in rows
    ]


@router.get("/verify/{certificate_number}", response_model=PublicCertificateOut)
async def verify_certificate(certificate_number: str, db: AsyncSession = Depends(get_db)):
    """Public endpoint — no auth required. Anyone with the certificate number
    (e.g. an employer, scanning the QR code) can confirm authenticity."""
    cert = (await db.execute(select(Certificate).where(Certificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None:
        return PublicCertificateOut(valid=False, invalid_reason="not_found")
    if cert.revoked_at is not None:
        return PublicCertificateOut(valid=False, invalid_reason="revoked")
    if _is_expired(cert):
        return PublicCertificateOut(valid=False, invalid_reason="expired")
    course = await db.get(Course, cert.course_id)
    student = await db.get(User, cert.student_id)
    return PublicCertificateOut(
        valid=True, certificate_number=cert.certificate_number,
        course_title=(course.title if course else cert.course_title),
        student_full_name=(student.full_name if student else None),
        grade=cert.grade, score_percent=cert.score_percent, skills=list(cert.skills_json or []),
        specialization=cert.specialization, instructor_name=cert.instructor_name,
        issued_at=cert.issued_at.isoformat(),
        expires_at=cert.expires_at.isoformat() if cert.expires_at else None,
        verify_url=verification_url(cert.certificate_number),
    )


@router.get("/{certificate_number}/qr")
async def certificate_qr(certificate_number: str, db: AsyncSession = Depends(get_db)):
    cert = (await db.execute(select(Certificate).where(Certificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None:
        raise NotFoundError("Certificate not found.")
    png_bytes = generate_qr_png_bytes(cert.certificate_number)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/{certificate_number}/pdf")
async def certificate_pdf(certificate_number: str, db: AsyncSession = Depends(get_db)):
    """Public, same access rules as /verify — a certificate is meant to be
    shown to anyone with the number. Returns a server-rendered PDF (weasyprint)
    matching the /certificates/view/[number] frontend page. If revoked or
    expired, this deliberately still 404s rather than serving a PDF of an
    invalid certificate."""
    cert = (await db.execute(select(Certificate).where(Certificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None or cert.revoked_at is not None or _is_expired(cert):
        raise NotFoundError("Certificate not found.")
    course = await db.get(Course, cert.course_id)
    student = await db.get(User, cert.student_id)
    try:
        pdf_bytes = generate_certificate_pdf_bytes(cert, course, student)
    except ImportError as exc:
        raise ServiceUnavailableError(
            "PDF generation is temporarily unavailable on this server. Use your browser's Print to PDF on the certificate page instead."
        ) from exc
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{cert.certificate_number}.pdf"'},
    )


@router.post("/{certificate_number}/revoke", response_model=RevokeCertificateOut)
async def revoke_certificate(
    certificate_number: str,
    admin: User = Depends(require_permission("certificates.manage")),
    db: AsyncSession = Depends(get_db),
):
    cert = (await db.execute(select(Certificate).where(Certificate.certificate_number == certificate_number))).scalar_one_or_none()
    if cert is None:
        raise NotFoundError("Certificate not found.")
    if cert.revoked_at is None:
        cert.revoked_at = datetime.now(UTC)
        await record_audit_event(db, actor_id=admin.id, action="certificate.revoke", resource_type="certificate", resource_id=str(cert.id))
        await db.commit()
    return RevokeCertificateOut(certificate_number=cert.certificate_number, revoked_at=cert.revoked_at.isoformat())
