from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_router
from app.config import get_settings
from app.core.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import HTTPSRedirectMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.websockets.chat import router as ws_chat_router

settings = get_settings()

# Error tracking (Sentry) — deliberately inert unless a real SENTRY_DSN is
# configured. No fake/placeholder DSN was fabricated for this build; this
# guard is what makes that honest rather than a silent no-op disguised as a
# working integration. See docs/OBSERVABILITY.md.
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
        # Request bodies can contain passwords/tokens on auth endpoints —
        # never send them to a third party by default.
        send_default_pii=False,
        max_request_body_size="never",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings.validate_for_production()
    # Roles/permissions are core, load-bearing data (register, RBAC checks,
    # etc. all depend on them existing) -- not optional demo content. Seeding
    # them here is safe because seed_rbac() is check-then-insert idempotent
    # (see app/seed.py): a fresh database gets them created once; a database
    # that already has them is a fast no-op read on every subsequent boot.
    # This makes any freshly-migrated database (new environment, restored
    # backup, etc.) self-healing instead of requiring someone to remember to
    # run `python -m app.seed` by hand before the app is actually usable.
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
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(RequestContextMiddleware)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_chat_router)

# /metrics — Prometheus scrape endpoint (request counts/latencies by
# path+method+status, Python/process metrics). Deliberately not
# authenticated: the standard pattern is to restrict it at the network layer
# (see infra/k8s/10-networkpolicy.yaml, which should only allow the
# in-cluster Prometheus to reach this port) rather than in application code.
# excluded_handlers keeps docs/metrics/health noise out of the metrics
# themselves.
Instrumentator(excluded_handlers=["/api/docs", "/api/redoc", "/api/openapi.json", "/metrics"]).instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)


@app.get("/")
async def root():
    return {"service": settings.APP_NAME, "status": "running", "docs": "/api/docs"}
