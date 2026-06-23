"""Helpers for the refresh-token HttpOnly cookie.

The access token is returned in the response body and kept only in the SPA's
memory. The refresh token is delivered exclusively via an HttpOnly, Secure,
SameSite cookie so that JavaScript — and therefore an XSS payload — can never
read it. The cookie is path-scoped to the login routes so it is only attached to
refresh/logout requests, never to regular API calls.
"""

from __future__ import annotations

from fastapi import Request, Response

from app.core.config import settings


def _cookie_path() -> str:
    return f"{settings.API_V1_STR}/login"


def set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the refresh token as an HttpOnly cookie to the response."""
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=_cookie_path(),
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def clear_refresh_cookie(response: Response) -> None:
    """Remove the refresh-token cookie (logout / failed rotation)."""
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=_cookie_path(),
        domain=settings.REFRESH_COOKIE_DOMAIN,
    )


def read_refresh_cookie(request: Request) -> str | None:
    """Return the refresh token carried by the request cookie, if any."""
    return request.cookies.get(settings.REFRESH_COOKIE_NAME)
