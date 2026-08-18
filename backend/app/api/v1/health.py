from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import check_db_health
from app.redis_client import check_redis_health

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health():
    """Liveness-ish general health summary."""
    db_ok = await check_db_health()
    redis_ok = await check_redis_health()
    # DB down => unhealthy (the app cannot serve). Redis down => degraded, not
    # unhealthy: rate limiting fails open by design, so a Redis outage must be
    # visible to monitoring without pulling the pod out of rotation (that is
    # what /ready is for, and it deliberately checks only the DB so a Redis
    # blip cannot trigger a restart storm).
    if not db_ok:
        status = "unhealthy"
    elif not redis_ok:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "version": settings.SERVICE_VERSION,
        "environment": settings.APP_ENV,
        "dependencies": {"database": db_ok, "redis": redis_ok},
    }


@router.get("/live")
async def live():
    """Kubernetes liveness probe — process is up. No dependency checks."""
    return {"status": "alive"}


@router.get("/ready")
async def ready():
    """Kubernetes readiness probe — can this instance serve traffic right now."""
    db_ok = await check_db_health()
    if not db_ok:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": False})
    return {"status": "ready", "database": True}
