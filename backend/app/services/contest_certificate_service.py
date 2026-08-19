from __future__ import annotations

import base64
import html
import io
from datetime import UTC, datetime, timedelta

import qrcode

from app.config import get_settings
from app.models.contest import ContestCertificate
from app.models.user import User

settings = get_settings()


def verification_url(certificate_number: str) -> str:
    return f"{settings.FRONTEND_URL}/contests/certificates/verify/{certificate_number}"


def generate_qr_png_bytes(certificate_number: str) -> bytes:
    image = qrcode.make(verification_url(certificate_number))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def certificate_expiry() -> datetime | None:
    if settings.CERTIFICATE_VALIDITY_DAYS is None:
        return None
    return datetime.now(UTC) + timedelta(days=settings.CERTIFICATE_VALIDITY_DAYS)


def _render_html(cert: ContestCertificate, student: User) -> str:
    qr_b64 = base64.b64encode(generate_qr_png_bytes(cert.certificate_number)).decode("ascii")
    valid_until = cert.expires_at.date().isoformat() if cert.expires_at else "Lifetime"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
@page {{ size:A4 landscape; margin:0; }}
html,body {{ margin:0; width:100%; height:100%; }}
body {{ font-family:DejaVu Sans,sans-serif; color:#f8fafc; background:#0b1020; }}
.frame {{ position:relative; box-sizing:border-box; width:100%; height:100%; padding:48px 64px; border:4px solid #d4af37; overflow:hidden; }}
.frame:before {{ content:'SURVIVAL SCHOOL'; position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:82px; font-weight:700; letter-spacing:14px; color:rgba(255,255,255,.03); transform:rotate(-18deg); }}
.eyebrow {{ color:#d4af37; letter-spacing:4px; text-transform:uppercase; font-size:12px; }}
h1 {{ font-size:40px; margin:10px 0 0; color:#fff; }}
.sub {{ color:#94a3b8; margin-top:6px; font-size:14px; }}
.student {{ font-size:30px; font-weight:700; margin-top:30px; }}
.award {{ color:#d4af37; font-size:18px; margin-top:4px; }}
.stats {{ display:flex; gap:12px; margin-top:24px; }}
.stat {{ padding:10px 16px; border:1px solid rgba(212,175,55,.5); background:rgba(212,175,55,.08); }}
.meta {{ color:#94a3b8; font-size:12px; line-height:1.7; }}
.footer {{ position:absolute; left:64px; right:64px; bottom:42px; display:flex; justify-content:space-between; align-items:flex-end; }}
.seal {{ width:74px; height:74px; border:2px solid #d4af37; border-radius:50%; display:flex; align-items:center; justify-content:center; text-align:center; color:#d4af37; font-size:10px; font-weight:700; }}
.qr {{ width:92px; height:92px; }}
</style></head><body><div class='frame'>
<div class='eyebrow'>Survival School · Contest Achievement</div>
<h1>{html.escape(cert.contest_title)}</h1>
<div class='sub'>Verified competitive achievement certificate</div>
<div class='student'>{html.escape(student.full_name if student else '')}</div>
<div class='award'>Placed #{cert.rank} in the contest</div>
<div class='stats'><div class='stat'>Score <strong>{cert.score_percent}%</strong></div><div class='stat'>Certificate <strong>{html.escape(cert.certificate_number)}</strong></div></div>
<div class='footer'><div class='meta'>Issued {cert.issued_at.date().isoformat()}<br/>Valid until {valid_until}<br/>Verification: {html.escape(verification_url(cert.certificate_number))}</div><div class='seal'>SS<br/>VERIFIED</div><img class='qr' src='data:image/png;base64,{qr_b64}' /></div>
</div></body></html>"""


def generate_pdf_bytes(cert: ContestCertificate, student: User) -> bytes:
    from weasyprint import HTML
    return HTML(string=_render_html(cert, student)).write_pdf()
