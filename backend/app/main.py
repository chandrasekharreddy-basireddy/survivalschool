from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import get_settings
from app.core.auth_cookie import AuthCookieMiddleware
from app.core.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import HTTPSRedirectMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.database import AsyncSessionLocal
from app.redis_client import get_redis
from app.services.registration_service import refresh_window
from app.websockets.chat import router as ws_chat_router

settings = get_settings()

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
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.SERVICE_VERSION,
    description="Production API for Survival School — MCQ-driven learning platform.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuthCookieMiddleware)
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(RequestContextMiddleware)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.middleware("http")
async def registration_window_guard(request, call_next):
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

Instrumentator(excluded_handlers=["/api/docs", "/api/redoc", "/api/openapi.json", "/metrics"]).instrument(app)


@app.get("/health")
async def health():
    checks = {"database": False, "redis": False}
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "checks": checks}) from exc
    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = True
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "checks": checks}) from exc
    return {"status": "healthy", "checks": checks, "version": settings.SERVICE_VERSION}


@app.get("/")
async def root():
    return {"service": settings.APP_NAME, "status": "running", "docs": "/api/docs", "health": "/health"}
