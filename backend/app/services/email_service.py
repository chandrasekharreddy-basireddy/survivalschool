"""Pluggable email delivery. Three real backends selected by EMAIL_BACKEND:

  * console -- dev only, prints the message to structured logs so a developer
    can read verification/reset links without a mail server.
  * resend  -- production. Sends over Resend's HTTPS API (port 443). This is
    the backend that actually works on Render: Render blocks outbound SMTP
    ports (25/465/587) at the network layer to prevent spam, so any smtplib
    connection there dies with "[Errno 101] Network is unreachable" no matter
    how correct the credentials are. An HTTPS API sidesteps that entirely.
  * smtp    -- classic SMTP via smtplib, for hosts that DO allow outbound
    SMTP (most self-hosted / VPS deployments). Kept because it's the right
    choice off Render, but it is NOT usable on Render's egress-restricted
    network.

Templates are Jinja2, responsive HTML with a plain-text fallback (spec
section 21).
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import httpx
import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import get_settings

settings = get_settings()
logger = structlog.get_logger("survivalschool.email")

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_template(name: str, **context) -> tuple[str, str]:
    html = _env.get_template(f"{name}.html").render(**context)
    text_template = f"{name}.txt"
    if (_TEMPLATE_DIR / text_template).exists():
        text = _env.get_template(text_template).render(**context)
    else:
        text = html
    return html, text


async def send_email(to: str, subject: str, template: str, **context) -> bool:
    html, text = render_template(template, **context, app_name=settings.APP_NAME)

    if settings.EMAIL_BACKEND == "console":
        # Dev convenience only: the console backend exists so a developer can read
        # verification/reset links without a real mail server. Never used in
        # production (validate_for_production() forbids EMAIL_BACKEND=console there),
        # and the real backends below never log message content.
        logger.info("email_sent_console", to=to, subject=subject, template=template, text_body=text)
        return True

    try:
        if settings.EMAIL_BACKEND == "resend":
            await _send_resend(to=to, subject=subject, html=html, text=text)
            logger.info("email_sent_resend", to=to, subject=subject, template=template)
            return True

        # smtplib path (non-Render hosts). smtplib is fully synchronous/blocking,
        # so it runs in a worker thread via asyncio.to_thread to keep the network
        # round trip off the asyncio event loop (otherwise one slow send freezes
        # every other in-flight request on this worker).
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        await asyncio.to_thread(_send_sync, msg)
        logger.info("email_sent_smtp", to=to, subject=subject, template=template)
        return True
    except Exception as exc:
        logger.error("email_send_failed", to=to, subject=subject, backend=settings.EMAIL_BACKEND, error=str(exc))
        return False


async def _send_resend(*, to: str, subject: str, html: str, text: str) -> None:
    """Send via Resend's HTTPS API (https://resend.com/docs/api-reference/emails/send-email).

    Uses httpx (already async, so no thread offload needed) over port 443 --
    the whole reason this backend exists is that Render's network blocks the
    SMTP ports, and HTTPS is not blocked. A non-2xx response is raised so the
    caller logs a real email_send_failed with the provider's actual error
    body rather than silently reporting success.
    """
    if not settings.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not configured but EMAIL_BACKEND=resend.")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.EMAIL_FROM,
                "to": [to],
                "subject": subject,
                "html": html,
                "text": text,
            },
        )
        if resp.status_code >= 400:
            # Surface Resend's real error (e.g. "domain is not verified",
            # "you can only send testing emails to your own address") so the
            # operator sees exactly what to fix, instead of a generic failure.
            raise RuntimeError(f"Resend API {resp.status_code}: {resp.text}")


def _send_sync(msg: EmailMessage) -> None:
    context_ssl = ssl.create_default_context()
    # An explicit timeout matters as much as the thread offload: without one,
    # smtplib's default has no bound, so a stalled TCP handshake can hang a
    # worker thread indefinitely instead of failing fast.
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls(context=context_ssl)
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
