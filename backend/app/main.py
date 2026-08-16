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
from app.core.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import HTTPSRedirectMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.database import AsyncSessionLocal
from app.redis_client import get_redis
from app.services.registration_service import refresh_window
from app.websockets.chat import router as ws_chat_router
