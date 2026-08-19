from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.config import get_settings

logger = structlog.get_logger("survivalschool.request")
settings = get_settings()

# Health-check paths are exempt from the HTTPS redirect: Kubernetes probes and
# load-balancer health checks commonly hit the pod directly over plain HTTP
# (they run inside the cluster network, never through the TLS-terminating
# ingress), so redirecting them would make every probe fail and the pod would
# be killed for "not being healthy" while actually serving traffic fine.
# All health routes live under the API prefix (app/api/v1/health.py); there
# are no bare /health or /live routes, so only the prefixed paths are listed.
_HTTPS_REDIRECT_EXEMPT_PATHS = {
    f"{settings.API_V1_PREFIX}/health",
    f"{settings.API_V1_PREFIX}/live",
    f"{settings.API_V1_PREFIX}/ready",
}


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirects HTTP -> HTTPS in production.

    Deliberately NOT Starlette's built-in HTTPSRedirectMiddleware, which only
    ever looks at `request.url.scheme` — behind a reverse proxy/ingress that
    terminates TLS (the standard production topology here, see
    docs/DEPLOYMENT.md), the connection FastAPI actually sees is always plain
    HTTP even when the original client request was HTTPS, so that check alone
    would redirect-loop every request. Instead this respects
    `X-Forwarded-Proto`, but ONLY when TRUST_PROXY_HEADERS is set (the same
    guardrail app/dependencies.py::get_client_ip() uses for X-Forwarded-For) —
    otherwise a spoofed header could be used to bypass the redirect entirely.
    """

    async def dispatch(self, request: Request, call_next):
        if settings.APP_ENV != "production" or request.url.path in _HTTPS_REDIRECT_EXEMPT_PATHS:
            return await call_next(request)

        if settings.TRUST_PROXY_HEADERS:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        else:
            scheme = request.url.scheme

        if scheme != "https":
            https_url = request.url.replace(scheme="https")
            return RedirectResponse(url=str(https_url), status_code=308)

        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attaches a request_id to every request/response and logs structured
    access lines. Request IDs propagate into error envelopes and audit logs
    (spec sections 28, 30)."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["x-request-id"] = request_id
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline OWASP-recommended security headers on every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        # Explicit per-directive policy rather than leaning on default-src alone.
        # These responses are API JSON, the /api/docs Swagger UI (dev/staging
        # only) and error pages; script-src/style-src 'self' keeps injected
        # inline scripts from executing, while 'unsafe-inline' on style-src is
        # the minimum Swagger UI needs. connect-src 'self' matches same-origin
        # XHR/fetch; img-src allows data: URIs used by the docs favicon.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
