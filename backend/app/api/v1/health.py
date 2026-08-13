from __future__ import annotations

from fastapi import APIRouter

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
    return {
        "status": "ok" if db_ok else "degraded",
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
        return {"status": "not_ready", "database": False}, 503
    return {"status": "ready", "database": True}
