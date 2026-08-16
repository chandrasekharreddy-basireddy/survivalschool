from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_router
from app.config import get_settings
from app.core.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import (
    HTTPSRedirectMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(RequestContextMiddleware)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_chat_router)

Instrumentator(
    excluded_handlers=["/api/docs", "/api/redoc", "/api/openapi.json", "/metrics"]
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/")
async def root():
    return {"service": settings.APP_NAME, "status": "running", "docs": "/api/docs"}
