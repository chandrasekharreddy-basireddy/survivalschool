from __future__ import annotations

import uuid

import structlog
from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as SATimeoutError

try:
    from asyncpg.exceptions import PostgresError
except ImportError:  # pragma: no cover - asyncpg is always installed outside tests using a different driver
    PostgresError = ()  # type: ignore[assignment]

# Both signal "no DB connection available right now" — PostgresError when the
# database/pooler itself rejects the connection (e.g. Supabase's pooler at
# its client cap), SATimeoutError when SQLAlchemy's own local pool queue
# (pool_size + max_overflow) fills up first and a checkout waits out
# pool_timeout without ever reaching the database at all. Load testing hit
# both: the first before DB_POOL_SIZE/DB_MAX_OVERFLOW were sized to the
# pooler's cap, the second under load heavy enough to fill even the
# corrected, smaller local pool.
_DB_UNAVAILABLE_ERRORS = (PostgresError, SATimeoutError)

logger = structlog.get_logger("survivalschool.errors")


class AppError(Exception):
    """Base application error. Every raised AppError produces a consistent,
    safe error envelope — never a raw stack trace or SQL error to the client
    (spec section 29)."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None):
        self.message = message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationAppError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_error"


class AuthorizationError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "authorization_error"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
                "details": exc.details,
            }
        },
    )


async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI/Pydantic's own request-parsing errors (a malformed body,
    wrong field type, missing required field, a Query/Path pattern
    mismatch) never went through AppError — they fell through to
    Starlette's default handler, which returns {"detail": [...]}
    instead of this app's {"error": {code, message, request_id, details}}
    envelope. Every route already relies on that one consistent shape
    (see app_error_handler above, and frontend/src/lib/api.ts's error
    parsing, which reads err.error.message) — a bare {"detail": [...]}
    body leaves err.message undefined there, so the UI falls back to
    the generic HTTP status text ("Unprocessable Entity") instead of
    telling the user which field was wrong."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    errors = jsonable_encoder(exc.errors())
    first = errors[0] if errors else None
    if first:
        loc = ".".join(str(p) for p in first["loc"] if p not in ("body", "query", "path"))
        message = f"{loc}: {first['msg']}" if loc else first["msg"]
    else:
        message = "Validation failed."
    # Pydantic's .errors() includes the raw submitted value under "input" for
    # every failed field — for a password-policy failure (RegisterRequest,
    # ResetPasswordRequest) that's the user's plaintext password, echoed back
    # into the HTTP response body and anything that logs it (proxies, error
    # trackers, browser devtools). The field location + message already tell
    # the client what's wrong; the client never needs its own submitted value
    # reflected back, so strip "input" from every error rather than trying to
    # enumerate which field names are sensitive.
    for error in errors:
        error.pop("input", None)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "code": "validation_error",
                "message": message,
                "request_id": request_id,
                "details": {"errors": errors},
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    # A genuinely unhandled exception (i.e. a real bug, not an AppError a
    # route raised on purpose) — this is exactly the class of event that
    # must never disappear silently. Always logged with a full traceback via
    # structlog regardless of whether Sentry is configured; also forwarded
    # to Sentry when SENTRY_DSN is set (capture_exception is a documented
    # no-op if sentry_sdk.init() was never called, so this is safe either
    # way — see app/main.py).
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        exc_info=exc,
    )
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except ImportError:
        pass

    # A raw PostgresError or SQLAlchemy pool TimeoutError surfacing here
    # (rather than an AppError a route raised on purpose) means no database
    # connection was available — either the pooler itself rejected the
    # connection (e.g. Supabase's session-mode pooler at its client cap) or
    # SQLAlchemy's own local pool queue filled up first and a checkout timed
    # out before ever reaching the database. Both are transient capacity
    # conditions, not a bug in this app: tell the client to retry (503)
    # instead of the generic "something is broken here" 500, which is both
    # more honest and lets a well-behaved client back off and succeed on its
    # own rather than surfacing a dead end.
    if isinstance(exc, _DB_UNAVAILABLE_ERRORS):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "The database is temporarily busy. Please try again in a moment.",
                    "request_id": request_id,
                    "details": {},
                }
            },
        )

    # Deliberately no str(exc) in the response — internal details never leak to clients.
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "request_id": request_id,
                "details": {},
            }
        },
    )
