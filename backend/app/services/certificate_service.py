from __future__ import annotations

import base64
import html
import io
import secrets
from datetime import UTC, datetime, timedelta

import qrcode
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.assessment import Exam, ExamAttempt, Quiz, QuizAttempt
from app.models.certificate import Certificate
from app.models.lms import Course
from app.models.user import User

settings = get_settings()

_GRADE_BANDS = (
    (95, "A+"),
    (85, "A"),
    (75, "B"),
    (70, "C"),
    (0, "Pass"),
)


def _grade_for_score(score_percent: int) -> str:
    for threshold, label in _GRADE_BANDS:
        if score_percent >= threshold:
            return label
    return "Pass"


async def _compute_grade_and_score(db: AsyncSession, student_id, course_id) -> tuple[str | None, int | None]:
    quiz_ids = (await db.execute(select(Quiz.id).where(Quiz.course_id == course_id))).scalars().all()
    exam_ids = (await db.execute(select(Exam.id).where(Exam.course_id == course_id))).scalars().all()
    best_scores: list[int] = []
    for quiz_id in quiz_ids:
        best = (await db.execute(
            select(QuizAttempt.score_percent)
            .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.student_id == student_id, QuizAttempt.status == "submitted", QuizAttempt.score_percent.is_not(None))
            .order_by(QuizAttempt.score_percent.desc()).limit(1)
        )).scalar_one_or_none()
        if best is not None:
            best_scores.append(best)
    for exam_id in exam_ids:
        best = (await db.execute(
            select(ExamAttempt.score_percent)
            .where(ExamAttempt.exam_id == exam_id, ExamAttempt.student_id == student_id, ExamAttempt.status == "submitted", ExamAttempt.score_percent.is_not(None))
            .order_by(ExamAttempt.score_percent.desc()).limit(1)
        )).scalar_one_or_none()
        if best is not None:
            best_scores.append(best)
    if not best_scores:
        return None, None
    score_percent = round(sum(best_scores) / len(best_scores))
    return _grade_for_score(score_percent), score_percent


def _generate_certificate_number() -> str:
    return f"SS-{secrets.token_hex(6).upper()}"


def certificate_expiry() -> datetime | None:
    if settings.CERTIFICATE_VALIDITY_DAYS is None:
        return None
    return datetime.now(UTC) + timedelta(days=settings.CERTIFICATE_VALIDITY_DAYS)


async def issue_certificate(db: AsyncSession, student: User, course: Course) -> Certificate:
    existing = (await db.execute(select(Certificate).where(Certificate.student_id == student.id, Certificate.course_id == course.id))).scalar_one_or_none()
    if existing:
        return existing
    grade, score_percent = await _compute_grade_and_score(db, student.id, course.id)
    instructor_name = None
    if course.instructor_id is not None:
        instructor = await db.get(User, course.instructor_id)
        instructor_name = instructor.full_name if instructor else None
    cert = Certificate(
        certificate_number=_generate_certificate_number(), student_id=student.id, course_id=course.id,
        course_title=course.title,
        grade=grade, score_percent=score_percent, skills_json=list(course.skills or []),
        specialization=course.specialization, instructor_name=instructor_name, expires_at=certificate_expiry(),
    )
    try:
        async with db.begin_nested():
            db.add(cert)
            await db.flush()
    except IntegrityError:
        return (await db.execute(select(Certificate).where(Certificate.student_id == student.id, Certificate.course_id == course.id))).scalar_one()
    return cert


def verification_url(certificate_number: str) -> str:
    return f"{settings.FRONTEND_URL}/verify/certificate/{certificate_number}"


def generate_qr_png_bytes(certificate_number: str) -> bytes:
    img = qrcode.make(verification_url(certificate_number))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_CERT_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
@page {{ size: A4 landscape; margin: 0; }}
body {{ margin:0; font-family:'DejaVu Sans',sans-serif; background:#0f172a; color:#f8fafc; width:100%; height:100%; }}
.frame {{ position:relative; box-sizing:border-box; width:100%; height:100%; padding:48px 64px; border:3px solid #c9a44c; overflow:hidden; }}
.watermark {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; transform:rotate(-18deg); font-size:78px; font-weight:700; letter-spacing:14px; color:rgba(255,255,255,.025); pointer-events:none; }}
.eyebrow {{ letter-spacing:4px; font-size:12px; color:#c9a44c; text-transform:uppercase; }}
h1 {{ font-size:42px; margin:8px 0 0 0; color:#ffffff; }}
.sub {{ font-size:14px; color:#94a3b8; margin-top:4px; }}
.student {{ font-size:30px; margin:28px 0 4px 0; color:#ffffff; font-weight:700; }}
.course {{ font-size:20px; color:#c9a44c; margin-bottom:4px; }}
.spec {{ font-size:13px; color:#94a3b8; margin-bottom:18px; }}
.grade-row {{ display:flex; align-items:center; gap:16px; margin-bottom:18px; }}
.grade-badge {{ display:inline-block; padding:6px 18px; border-radius:999px; border:1.5px solid #c9a44c; color:#c9a44c; font-weight:700; font-size:16px; box-shadow:0 0 0 2px rgba(201,164,76,.08), inset 0 1px 3px rgba(255,255,255,.06); }}
.score {{ color:#f8fafc; font-size:14px; }}
.skills {{ font-size:12px; color:#94a3b8; margin-bottom:18px; }}
.skill-chip {{ display:inline-block; padding:3px 10px; margin:2px 4px 2px 0; border-radius:6px; background:rgba(201,164,76,.12); border:1px solid rgba(201,164,76,.4); color:#e2c78a; }}
.signatures {{ position:absolute; left:64px; bottom:86px; display:flex; gap:36px; }}
.signature {{ width:170px; border-top:1px solid rgba(201,164,76,.7); padding-top:5px; font-size:10px; color:#94a3b8; }}
.footer {{ position:absolute; bottom:42px; left:64px; right:64px; display:flex; justify-content:space-between; align-items:flex-end; }}
.meta {{ font-size:11px; color:#64748b; line-height:1.6; }}
.qr {{ width:90px; height:90px; }}
.seal {{ width:72px; height:72px; border-radius:50%; border:2px solid #c9a44c; box-shadow:0 0 0 4px rgba(201,164,76,.06), inset 0 2px 4px rgba(255,255,255,.08); display:flex; align-items:center; justify-content:center; color:#c9a44c; font-size:10px; text-align:center; font-weight:700; }}
</style></head><body>
<div class="frame">
<div class="watermark">SURVIVAL SCHOOL</div>
<div class="eyebrow">Survival School &mdash; Certificate of Completion</div>
<h1>{course_title}</h1>
<div class="sub">{specialization_line}</div>
<div class="student">{student_name}</div>
<div class="course">has successfully completed this course</div>
<div class="grade-row">{grade_badge}{score_line}</div>
<div class="skills">{skills_html}</div>
<div class="signatures"><div class="signature">Instructor / Course Lead</div><div class="signature">Survival School</div></div>
<div class="footer"><div class="meta">Certificate No. {cert_number}<br/>Issued {issued_at}{expires_line}<br/>{instructor_line}</div><div class="seal">SS<br/>VERIFIED</div><img class="qr" src="data:image/png;base64,{qr_base64}" /></div>
</div></body></html>"""


def render_certificate_html(cert: Certificate, course: Course, student: User) -> str:
    grade_badge = f'<span class="grade-badge">{html.escape(cert.grade)}</span>' if cert.grade else ""
    score_line = f'<span class="score">{cert.score_percent}% overall score</span>' if cert.score_percent is not None else ""
    skills = list(cert.skills_json or [])
    skills_html = "".join(f'<span class="skill-chip">{html.escape(s)}</span>' for s in skills) if skills else ""
    specialization_line = html.escape(cert.specialization) if cert.specialization else "Professional Certification Track"
    instructor_line = f"Instructor: {html.escape(cert.instructor_name)}" if cert.instructor_name else ""
    expires_line = f"<br/>Valid until {cert.expires_at.date().isoformat()}" if cert.expires_at else ""
    qr_base64 = base64.b64encode(generate_qr_png_bytes(cert.certificate_number)).decode("ascii")
    return _CERT_HTML_TEMPLATE.format(
        course_title=html.escape(course.title if course else ""), specialization_line=specialization_line,
        student_name=html.escape(student.full_name if student else ""), grade_badge=grade_badge, score_line=score_line,
        skills_html=skills_html, cert_number=html.escape(cert.certificate_number), issued_at=cert.issued_at.date().isoformat(),
        expires_line=expires_line, instructor_line=instructor_line, qr_base64=qr_base64,
    )


def generate_certificate_pdf_bytes(cert: Certificate, course: Course, student: User) -> bytes:
    from weasyprint import HTML
    return HTML(string=render_certificate_html(cert, course, student)).write_pdf()
