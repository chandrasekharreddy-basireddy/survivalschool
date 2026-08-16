from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

settings = get_settings()

ACCESS_COOKIE = "ss_access_token"
REFRESH_COOKIE = "ss_refresh_token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
COOKIE_TOKEN_ENDPOINTS = {
    f"{settings.API_V1_PREFIX}/auth/login",
    f"{settings.API_V1_PREFIX}/auth/2fa/verify-login",
    f"{settings.API_V1_PREFIX}/auth/refresh",
}


def _secure_cookie() -> bool:
    return settings.APP_ENV in {"production", "staging"}


def _same_site() -> str:
    return "none" if _secure_cookie() else "lax"


def set_auth_cookies(response: Response, *, access_token: str, refresh_token: str, refresh_max_age: int) -> None:
    secure = _secure_cookie()
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        httponly=True,
        secure=secure,
        samesite=_same_site(),
        path="/",
        max_age=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=secure,
        samesite=_same_site(),
        path=f"{settings.API_V1_PREFIX}/auth",
        max_age=refresh_max_age,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=f"{settings.API_V1_PREFIX}/auth")


class AuthCookieMiddleware(BaseHTTPMiddleware):
    """Bridge the existing token API into a safer browser cookie session.

    Browser requests opt into cookie mode with X-Auth-Mode: cookie. Access and
    refresh tokens are placed in HttpOnly cookies and stripped from the browser
    response body. Legacy API clients continue receiving the existing JSON token
    response when they do not send that header.

    Because production cookies are SameSite=None (frontend and API are separate
    sites), state-changing cookie-authenticated requests also require a trusted
    Origin. This closes the CSRF window without forcing a shared-domain design.
    """

    async def dispatch(self, request: Request, call_next):
        cookie_mode = request.headers.get("x-auth-mode", "").lower() == "cookie"
        if cookie_mode and request.method in UNSAFE_METHODS and request.cookies.get(ACCESS_COOKIE):
            origin = request.headers.get("origin")
            if origin and origin not in settings.cors_origins_list:
                return JSONResponse(
                    status_code=403,
                    content={"message": "Cross-origin request rejected.", "code": "csrf_origin_rejected"},
                )

        response = await call_next(request)
        if not cookie_mode:
            return response

        if request.url.path in COOKIE_TOKEN_ENDPOINTS and response.status_code == 200:
            body = b"".join([chunk async for chunk in response.body_iterator])
            try:
                data: dict[str, Any] = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return response

            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            if not access_token or not refresh_token:
                return response

            safe_body = {
                "token_type": "cookie",
                "expires_in": data.get("expires_in", settings.ACCESS_TOKEN_TTL_MINUTES * 60),
            }
            new_response = JSONResponse(content=safe_body, status_code=response.status_code)
            set_auth_cookies(
                new_response,
                access_token=access_token,
                refresh_token=refresh_token,
                refresh_max_age=settings.REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60,
            )
            return new_response

        if request.url.path in {
            f"{settings.API_V1_PREFIX}/auth/logout",
            f"{settings.API_V1_PREFIX}/auth/logout-all",
        } and response.status_code == 200:
            clear_auth_cookies(response)
        return response
