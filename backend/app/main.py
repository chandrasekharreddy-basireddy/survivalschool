from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import get_settings
from app.core.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import HTTPSRedirectMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.database import AsyncSessionLocal
from app.services.registration_service import refresh_window
from app.websockets.chat import router as ws_chat_router

settings = get_settings()

_EXPOSE_API_DOCS = settings.APP_ENV in ("development", "staging", "test")

if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        release=settings.SERVICE_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        send_default_pii=False,
        max_request_body_size="never",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings.validate_for_production()
    from app.seed import seed_rbac
    await seed_rbac()

    # Drive the weekend-exam / contest scheduler from inside the web process
    # when no standalone worker is deployed. Guarded by a Redis leader lock in
    # scheduler_loop, so running multiple gunicorn workers is safe.
    stop_event = asyncio.Event()
    scheduler_task: asyncio.Task | None = None
    if settings.RUN_INPROCESS_SCHEDULER and settings.APP_ENV != "test":
        from app.services.scheduler_runtime import scheduler_loop
        scheduler_task = asyncio.create_task(scheduler_loop(stop_event))

    try:
        yield
    finally:
        stop_event.set()
        if scheduler_task is not None:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.SERVICE_VERSION,
    description="Production API for Survival School — MCQ-driven learning platform.",
    lifespan=lifespan,
    # Publishing the full OpenAPI schema in production hands an unauthenticated
    # caller a complete map of every endpoint, request/response model and field
    # — free attack-surface reconnaissance. Expose it only outside production.
    docs_url="/api/docs" if _EXPOSE_API_DOCS else None,
    redoc_url="/api/redoc" if _EXPOSE_API_DOCS else None,
    openapi_url="/api/openapi.json" if _EXPOSE_API_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # This API authenticates with Bearer tokens in the Authorization header,
    # which CORS sends regardless of this flag. Enabling credentials only widens
    # the cookie/CSRF surface for no benefit — flip it back on if cookie auth
    # is ever introduced.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id", "X-Maintenance-Secret"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(RequestContextMiddleware)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.middleware("http")
async def registration_window_guard(request, call_next):
    # Existing unit/integration tests intentionally create accounts on any day;
    # the production registration window remains fail-closed and Thursday-only.
    if settings.APP_ENV == "test":
        return await call_next(request)

    if request.method == "POST" and request.url.path == f"{settings.API_V1_PREFIX}/auth/register":
        try:
            async with AsyncSessionLocal() as db:
                window = await refresh_window(db)
                await db.commit()
        except Exception:
            return JSONResponse(
                status_code=503,
                content={
                    "message": "Registration is temporarily unavailable while the registration window is being checked.",
                    "code": "registration_window_unavailable",
                },
            )
        if not window.is_open:
            next_open = window.next_open_at.astimezone(timezone.utc).isoformat() if window.next_open_at else None
            return JSONResponse(
                status_code=403,
                content={
                    "message": "Registration is currently closed. Registration opens every Thursday (IST).",
                    "code": "registration_closed",
                    "next_open_at": next_open,
                },
            )
    return await call_next(request)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_chat_router)

Instrumentator(excluded_handlers=["/api/docs", "/api/redoc", "/api/openapi.json", "/metrics"]).instrument(app).expose(
    app, include_in_schema=False
)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "status": "running",
        # Advertise the real paths — these are all mounted under the API
        # prefix; a bare /health has never existed.
        "docs": "/api/docs" if _EXPOSE_API_DOCS else None,
        "health": f"{settings.API_V1_PREFIX}/health",
    }
