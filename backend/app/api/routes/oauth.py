"""Social OAuth 2.0 endpoints — Google and Microsoft.

Flow (Authorization Code):
  1. GET /auth/{provider}/login
       → stores state in Redis (TTL 5 min)
       → 302 redirect to provider authorization page

  2. GET /auth/{provider}/callback?code=...&state=...
       → verifies state from Redis
       → exchanges code for access token (via httpx)
       → fetches user info from provider
       → finds or creates local User
       → creates/updates UserOAuthLink
       → 302 redirect to FRONTEND_OAUTH_REDIRECT_URL?access_token=...&refresh_token=...

No authlib dependency: uses httpx for HTTP calls and Redis for state.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import RedisDep, SessionDep
from app.core import security
from app.core.config import settings
from app.core.errors import AppError
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import crud_user
from app.features.user.models.oauth_link import UserOAuthLink
from app.features.user.models.user import User, UserCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["oauth"])

_STATE_TTL = 300  # seconds
_STATE_PREFIX = "oauth:state:"

# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_MICROSOFT_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"

_SUPPORTED_PROVIDERS = {"google", "microsoft"}


def _check_provider(provider: str) -> None:
    if provider not in _SUPPORTED_PROVIDERS:
        raise AppError(
            code="oauth.provider.unsupported",
            status_code=400,
            message=f"Fournisseur OAuth non supporté : {provider!r}. "
            f"Valeurs acceptées : {sorted(_SUPPORTED_PROVIDERS)}",
            details={"provider": provider},
        )


def _check_configured(provider: str) -> None:
    if provider == "google" and not (
        settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET
    ):
        raise AppError(
            code="oauth.provider.not_configured",
            status_code=503,
            message="La connexion via Google n'est pas configurée sur ce serveur.",
            details={"provider": "google"},
        )
    if provider == "microsoft" and not (
        settings.MICROSOFT_CLIENT_ID and settings.MICROSOFT_CLIENT_SECRET
    ):
        raise AppError(
            code="oauth.provider.not_configured",
            status_code=503,
            message="La connexion via Microsoft n'est pas configurée sur ce serveur.",
            details={"provider": "microsoft"},
        )


def _callback_url(request: Request, provider: str) -> str:
    """Build the redirect_uri sent to the OAuth provider."""
    base = settings.OAUTH_REDIRECT_BASE_URL.rstrip("/") if settings.OAUTH_REDIRECT_BASE_URL else str(request.base_url).rstrip("/")
    return f"{base}{settings.API_V1_STR}/auth/{provider}/callback"


def _authorization_url(provider: str, *, redirect_uri: str, state: str) -> str:
    if provider == "google":
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
        }
        return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"
    # microsoft
    tenant = settings.MICROSOFT_TENANT_ID or "common"
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile User.Read",
        "state": state,
        "response_mode": "query",
    }
    auth_url = _MICROSOFT_AUTH_URL.format(tenant=tenant)
    return f"{auth_url}?{urlencode(params)}"


async def _exchange_code(
    provider: str, *, code: str, redirect_uri: str
) -> dict[str, Any]:
    """Exchange authorization code for access token."""
    if provider == "google":
        token_url = _GOOGLE_TOKEN_URL
        data = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    else:
        tenant = settings.MICROSOFT_TENANT_ID or "common"
        token_url = _MICROSOFT_TOKEN_URL.format(tenant=tenant)
        data = {
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": "openid email profile User.Read",
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(token_url, data=data)

    if resp.status_code != 200:
        logger.warning(
            "OAuth token exchange failed: provider=%s status=%s body=%s",
            provider,
            resp.status_code,
            resp.text[:200],
        )
        raise AppError(
            code="oauth.token.exchange_failed",
            status_code=502,
            message="Impossible d'obtenir le token OAuth auprès du fournisseur.",
            details={"provider": provider},
        )
    return resp.json()


async def _fetch_user_info(provider: str, access_token: str) -> dict[str, Any]:
    """Fetch user profile from provider using the access token."""
    if provider == "google":
        url = _GOOGLE_USERINFO_URL
    else:
        url = _MICROSOFT_USERINFO_URL

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        logger.warning(
            "OAuth userinfo fetch failed: provider=%s status=%s",
            provider,
            resp.status_code,
        )
        raise AppError(
            code="oauth.userinfo.fetch_failed",
            status_code=502,
            message="Impossible de récupérer les informations utilisateur auprès du fournisseur.",
            details={"provider": provider},
        )
    return resp.json()


def _extract_user_info(provider: str, info: dict[str, Any]) -> tuple[str, str, str]:
    """Return (provider_user_id, email, full_name) from raw provider profile."""
    if provider == "google":
        provider_uid = info.get("sub", "")
        email = info.get("email", "")
        full_name = info.get("name", "")
    else:
        # Microsoft Graph
        provider_uid = info.get("id", "")
        email = (
            info.get("mail")
            or info.get("userPrincipalName")
            or info.get("email")
            or ""
        )
        full_name = info.get("displayName", "")
    return str(provider_uid), str(email).lower().strip(), str(full_name)


def _build_token_bundle(user_id: uuid.UUID) -> tuple[str, str, str, datetime]:
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_jti = str(uuid.uuid4())
    access_tok = security.create_access_token(user_id, expires_delta=access_token_expires)
    refresh_tok = security.create_refresh_token(
        user_id, expires_delta=refresh_token_expires, jti=refresh_jti
    )
    refresh_expires_at = datetime.now(timezone.utc) + refresh_token_expires
    return access_tok, refresh_tok, refresh_jti, refresh_expires_at


def _frontend_redirect(access_token: str, refresh_token: str) -> RedirectResponse:
    base = settings.FRONTEND_OAUTH_REDIRECT_URL or settings.FRONTEND_HOST
    params = urlencode({"access_token": access_token, "refresh_token": refresh_token})
    return RedirectResponse(url=f"{base}?{params}", status_code=302)


def _frontend_error_redirect(error: str) -> RedirectResponse:
    base = settings.FRONTEND_OAUTH_REDIRECT_URL or settings.FRONTEND_HOST
    params = urlencode({"oauth_error": error})
    return RedirectResponse(url=f"{base}?{params}", status_code=302)


async def _find_or_create_user(
    session: AsyncSession, *, provider: str, provider_uid: str, email: str, full_name: str
) -> User:
    """Find or create a local User for the given OAuth identity.

    Priority:
    1. Existing UserOAuthLink for (provider, provider_uid) → return linked user
    2. Existing User with matching email → link OAuth account + return user
    3. No user → create user (random password) + link
    """
    # 1. Lookup by OAuth link
    link_result = await session.exec(
        select(UserOAuthLink).where(
            UserOAuthLink.provider == provider,
            UserOAuthLink.provider_user_id == provider_uid,
        )
    )
    existing_link = link_result.first()
    if existing_link is not None:
        user = await session.get(User, existing_link.user_id)
        if user and user.is_active:
            return user

    # 2. Lookup by email
    user = await crud_user.get_by_email(session, email=email)

    # 3. Create user if not found
    if user is None:
        random_password = secrets.token_urlsafe(32)
        user_create = UserCreate(
            email=email,
            password=random_password,
            full_name=full_name or None,
            is_active=True,
            is_verified=True,
        )
        user = await crud_user.create_draft(session=session, data=user_create, user=None)
        await session.flush()

    # Create/update OAuth link
    if existing_link is None:
        session.add(
            UserOAuthLink(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_uid,
                email_at_link=email,
            )
        )
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{provider}/login")
async def oauth_login(
    provider: str,
    request: Request,
    redis: RedisDep,
) -> RedirectResponse:
    """Redirect the browser to the provider OAuth authorization page.

    Generates a CSRF state token stored in Redis (TTL 5 min).
    """
    _check_provider(provider)
    _check_configured(provider)

    state = secrets.token_urlsafe(24)
    await redis.setex(f"{_STATE_PREFIX}{state}", _STATE_TTL, provider.encode())

    redirect_uri = _callback_url(request, provider)
    auth_url = _authorization_url(provider, redirect_uri=redirect_uri, state=state)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/{provider}/callback", name="oauth_callback")
async def oauth_callback(
    provider: str,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle the OAuth provider callback.

    Exchanges the authorization code, resolves the user, issues JWT tokens,
    and redirects the browser to the frontend with the tokens in query params.
    """
    _check_provider(provider)

    # Provider returned an error (user denied, etc.)
    if error:
        logger.info("OAuth callback error from provider=%s error=%s", provider, error)
        return _frontend_error_redirect(error)

    if not code or not state:
        return _frontend_error_redirect("missing_code_or_state")

    # Verify + consume state (replay protection)
    stored = await redis.getdel(f"{_STATE_PREFIX}{state}")
    if stored is None or stored.decode() != provider:
        logger.warning("OAuth state mismatch: provider=%s state=%s", provider, state)
        return _frontend_error_redirect("invalid_state")

    try:
        redirect_uri = _callback_url(request, provider)
        token_data = await _exchange_code(provider, code=code, redirect_uri=redirect_uri)
        access_token_provider = token_data.get("access_token", "")
        user_info = await _fetch_user_info(provider, access_token_provider)
        provider_uid, email, full_name = _extract_user_info(provider, user_info)
    except AppError as exc:
        logger.warning("OAuth exchange/userinfo failed: %s", exc)
        return _frontend_error_redirect("provider_error")

    if not email or not provider_uid:
        logger.warning(
            "OAuth provider=%s returned empty email or uid — aborting", provider
        )
        return _frontend_error_redirect("missing_user_info")

    try:
        user = await _find_or_create_user(
            session,
            provider=provider,
            provider_uid=provider_uid,
            email=email,
            full_name=full_name,
        )
    except Exception:
        logger.exception("Error creating/linking OAuth user: provider=%s email=%s", provider, email)
        await session.rollback()
        return _frontend_error_redirect("server_error")

    # Keep parity with classic password login: inactive users must not be able
    # to authenticate through OAuth.
    if not user.is_active:
        logger.info(
            "OAuth login blocked for inactive user: provider=%s user=%s email=%s",
            provider,
            user.id,
            email,
        )
        await session.rollback()
        return _frontend_error_redirect("user_inactive")

    access_tok, refresh_tok, refresh_jti, refresh_expires_at = _build_token_bundle(user.id)
    # create_for_user internally calls CrudBase.create which commits the transaction,
    # flushing the pending user + oauth_link writes alongside the refresh token.
    await crud_user_refresh_token.create_for_user(
        session=session,
        user_id=user.id,
        jti=refresh_jti,
        expires_at=refresh_expires_at,
        user=user,
    )

    logger.info(
        "OAuth login success: provider=%s user=%s (email=%s)", provider, user.id, email
    )
    return _frontend_redirect(access_tok, refresh_tok)
