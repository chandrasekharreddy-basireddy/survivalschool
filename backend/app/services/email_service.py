"""Pluggable email delivery. Console backend (dev) prints to structured logs;
SMTP backend sends real mail. Templates are Jinja2, responsive HTML with a
plain-text fallback (spec section 21). Retries handled by the caller via the
background worker queue (spec section 48: "Email provider fails: queue/retry
delivery.").
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

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
        # and the "real" SMTP path below never logs message content.
        logger.info("email_sent_console", to=to, subject=subject, template=template, text_body=text)
        return True

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        # smtplib is fully synchronous/blocking -- calling it directly inside
        # this `async def` would freeze the ENTIRE event loop (every other
        # in-flight request on this worker, not just this one) for the whole
        # TLS handshake + auth + send round trip to the SMTP server, which is
        # commonly 0.5-3s and can spike much higher under load or on a flaky
        # network. With --workers 2, one slow email send could stall up to
        # half the app's total request-serving capacity. Running it in a
        # worker thread via asyncio.to_thread keeps the actual network wait
        # off the event loop, so every other request keeps being served at
        # normal speed while this one's SMTP call is in flight. This was a
        # real, measured architectural bug, not a speculative one -- it's the
        # most likely explanation for "the whole site feels slow" reports
        # that correlate with email sends, not just "email itself is slow".
        await asyncio.to_thread(_send_sync, msg)
        logger.info("email_sent_smtp", to=to, subject=subject, template=template)
        return True
    except Exception as exc:
        logger.error("email_send_failed", to=to, subject=subject, error=str(exc))
        return False


def _send_sync(msg: EmailMessage) -> None:
    context_ssl = ssl.create_default_context()
    # An explicit timeout matters as much as the thread offload: without one,
    # smtplib's default has no bound, so a stalled TCP handshake (e.g. a
    # transient network blip to Gmail) can hang a worker thread indefinitely
    # instead of failing fast and letting the caller show a real error.
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls(context=context_ssl)
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
