from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings

settings = get_settings()

ACCESS_COOKIE = "ss_access_token"
REFRESH_COOKIE = "ss_refresh_token"


def _secure_cookie() -> bool:
    return settings.APP_ENV in {"production", "staging"}


def _same_site() -> str:
    # The production frontend (Vercel) and backend (Render) are different
    # sites, so cross-site cookies need SameSite=None. Local development is
    # served over plain HTTP, where SameSite=Lax is the practical default.
    return "none" if _secure_cookie() else "lax"


def set_auth_cookies(response: Response, *, access_token: str, refresh_token: str, refresh_max_age: int) -> None:
    secure = _secure_cookie()
    same_site = _same_site()
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        httponly=True,
        secure=secure,
        samesite=same_site,
        path="/",
        max_age=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=secure,
        samesite=same_site,
        path=f"{settings.API_V1_PREFIX}/auth",
        max_age=refresh_max_age,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=f"{settings.API_V1_PREFIX}/auth")


class AuthCookieMiddleware(BaseHTTPMiddleware):
    """Bridge existing token JSON responses into browser HttpOnly cookies.

    Legacy/non-browser clients still receive the JSON token payload. Browser
    clients opt into cookie mode with `X-Auth-Mode: cookie`; cookies are set
    server-side and JavaScript never needs to persist bearer tokens.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.headers.get("x-auth-mode", "").lower() != "cookie":
            return response

        if request.url.path in {
            f"{settings.API_V1_PREFIX}/auth/login",
            f"{settings.API_V1_PREFIX}/auth/2fa/verify-login",
            f"{settings.API_V1_PREFIX}/auth/refresh",
        } and response.status_code == 200:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            try:
                data: dict[str, Any] = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return response
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            if access_token and refresh_token:
                set_auth_cookies(
                    response,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    refresh_max_age=settings.REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60,
                )
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        if request.url.path in {
            f"{settings.API_V1_PREFIX}/auth/logout",
            f"{settings.API_V1_PREFIX}/auth/logout-all",
        } and response.status_code == 200:
            clear_auth_cookies(response)
        return response
