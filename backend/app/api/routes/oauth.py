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

Account takeover rules (review of 30/09/2026, « nOAuth »): an e-mail returned by
a provider is only trusted when the provider vouches for it — Google's
``email_verified``, a personal Microsoft account, the shop's own Microsoft
tenant, or the ``xms_edov`` claim. An unverified e-mail never creates an
account nor links to an existing one. A superuser account is never linked nor
signed in through OAuth: administrators use their password.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import RedisDep, SessionDep
from app.core import security
from app.core.auth_cookies import set_refresh_cookie
from app.core.config import settings
from app.core.errors import AppError
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import crud_user, mark_logged_in
from app.features.user.models.oauth_link import UserOAuthLink
from app.features.user.models.user import User
from app.features.user.services.invitation import unusable_password_hash

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

# Personal Microsoft accounts (outlook.com, hotmail…) all belong to this tenant;
# Microsoft owns and verifies their addresses.
_MSA_CONSUMER_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"
# Multi-tenant endpoints: any Entra directory can sign in, and its admins can
# put any address in `mail` — never trusted on their own.
_MICROSOFT_MULTI_TENANT = {"common", "organizations", "consumers"}
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@dataclass(frozen=True)
class OAuthIdentity:
    """What the provider says about the person signing in."""

    provider_user_id: str
    email: str
    full_name: str
    email_verified: bool


class OAuthRefused(Exception):
    """The identity cannot be used here; ``code`` goes to the front as
    ``oauth_error``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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
    base = (
        settings.OAUTH_REDIRECT_BASE_URL.rstrip("/")
        if settings.OAUTH_REDIRECT_BASE_URL
        else str(request.base_url).rstrip("/")
    )
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
    return cast("dict[str, Any]", resp.json())


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
    return cast("dict[str, Any]", resp.json())


def _id_token_claims(token_data: dict[str, Any]) -> dict[str, Any]:
    """Claims of the ``id_token`` returned by the token endpoint.

    The token comes straight from the provider's token endpoint over TLS,
    authenticated with our client secret, so its signature need not be checked
    (OpenID Connect Core §3.1.3.7). An absent or malformed token gives ``{}``:
    the caller then treats the e-mail as unverified.
    """
    raw = token_data.get("id_token")
    if not isinstance(raw, str) or raw.count(".") != 2:
        return {}
    payload = raw.split(".")[1]
    try:
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        claims = json.loads(decoded)
    except (binascii.Error, ValueError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _is_true(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "1"}


def _microsoft_email_verified(claims: dict[str, Any]) -> bool:
    """Whether Microsoft vouches for the address of this sign-in."""
    if _is_true(claims.get("xms_edov")):
        # Optional claim: the tenant proved it owns the address's domain.
        return True
    tenant_id = str(claims.get("tid") or "").lower()
    if tenant_id == _MSA_CONSUMER_TENANT_ID:
        return True
    configured = (settings.MICROSOFT_TENANT_ID or "common").strip().lower()
    if configured in _MICROSOFT_MULTI_TENANT:
        return False
    # Single-tenant app: only the shop's own directory can sign in, and the shop
    # controls its addresses. A GUID is also checked against the token.
    return not _GUID.match(configured) or configured == tenant_id


def _extract_user_info(
    provider: str, info: dict[str, Any], id_claims: dict[str, Any]
) -> OAuthIdentity:
    """Identity from the raw provider profile and the id_token claims."""
    if provider == "google":
        provider_uid = info.get("sub", "")
        email = info.get("email", "")
        full_name = info.get("name", "")
        verified = _is_true(info.get("email_verified"))
    else:
        # Microsoft Graph
        provider_uid = info.get("id", "")
        email = (
            info.get("mail") or info.get("userPrincipalName") or info.get("email") or ""
        )
        full_name = info.get("displayName", "")
        verified = _microsoft_email_verified(id_claims)
    return OAuthIdentity(
        provider_user_id=str(provider_uid),
        email=str(email).lower().strip(),
        full_name=str(full_name),
        email_verified=verified,
    )


def _build_token_bundle(user_id: uuid.UUID) -> tuple[str, str, str, datetime]:
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_jti = str(uuid.uuid4())
    access_tok = security.create_access_token(
        user_id, expires_delta=access_token_expires
    )
    refresh_tok = security.create_refresh_token(
        user_id, expires_delta=refresh_token_expires, jti=refresh_jti
    )
    refresh_expires_at = datetime.now(timezone.utc) + refresh_token_expires
    return access_tok, refresh_tok, refresh_jti, refresh_expires_at


def _frontend_redirect(refresh_token: str) -> RedirectResponse:
    """Redirect to the SPA with the refresh token set as an HttpOnly cookie.

    No token is placed in the URL: the SPA obtains its in-memory access token by
    calling /login/refresh-token (which reads the cookie) right after landing.
    """
    base = settings.FRONTEND_OAUTH_REDIRECT_URL or settings.FRONTEND_HOST
    redirect = RedirectResponse(url=base, status_code=302)
    set_refresh_cookie(redirect, refresh_token)
    return redirect


def _frontend_error_redirect(error: str) -> RedirectResponse:
    base = settings.FRONTEND_OAUTH_REDIRECT_URL or settings.FRONTEND_HOST
    params = urlencode({"oauth_error": error})
    return RedirectResponse(url=f"{base}?{params}", status_code=302)


async def _find_or_create_user(
    session: AsyncSession, *, provider: str, identity: OAuthIdentity
) -> User:
    """Find or create the local User for an OAuth identity.

    1. An existing link (provider, provider uid) → its user, active or not (the
       caller blocks inactive accounts); never a superuser.
    2. An account with the same e-mail → linked, only if the provider verified
       the address and the account is not a superuser.
    3. No account → created, only if the provider verified the address.

    Raises ``OAuthRefused`` otherwise.
    """
    link_result = await session.exec(
        select(UserOAuthLink).where(
            UserOAuthLink.provider == provider,
            UserOAuthLink.provider_user_id == identity.provider_user_id,
        )
    )
    existing_link = link_result.first()
    if existing_link is not None:
        linked = await session.get(User, existing_link.user_id)
        if linked is not None:
            if linked.is_superuser:
                raise OAuthRefused(
                    "superuser_oauth_disabled",
                    "OAuth sign-in is disabled for administrator accounts",
                )
            return linked

    if not identity.email_verified:
        raise OAuthRefused(
            "email_not_verified",
            f"{provider} did not verify {identity.email!r}",
        )

    user = await crud_user.get_by_email(session, email=identity.email)
    if user is not None and user.is_superuser:
        # Never hand an administrator account to whoever controls a provider
        # account with the same address.
        raise OAuthRefused(
            "account_exists",
            "an administrator account uses this e-mail; sign in with the password",
        )

    if user is None:
        # Built directly, like the signup: the CRUD's model_dump drops the
        # excluded hashed_password of UserCreate, and the column is NOT NULL.
        # The password is one nobody knows; « mot de passe oublié » sets one.
        user = User(
            email=identity.email,
            full_name=identity.full_name or None,
            is_active=True,
            is_verified=True,
            hashed_password=unusable_password_hash(),
        )
        session.add(user)
        await session.flush()

    if existing_link is None:
        session.add(
            UserOAuthLink(
                user_id=user.id,
                provider=provider,
                provider_user_id=identity.provider_user_id,
                email_at_link=identity.email,
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
        token_data = await _exchange_code(
            provider, code=code, redirect_uri=redirect_uri
        )
        access_token_provider = token_data.get("access_token", "")
        user_info = await _fetch_user_info(provider, access_token_provider)
        identity = _extract_user_info(provider, user_info, _id_token_claims(token_data))
    except AppError as exc:
        logger.warning("OAuth exchange/userinfo failed: %s", exc)
        return _frontend_error_redirect("provider_error")

    email = identity.email
    if not email or not identity.provider_user_id:
        logger.warning(
            "OAuth provider=%s returned empty email or uid — aborting", provider
        )
        return _frontend_error_redirect("missing_user_info")

    try:
        user = await _find_or_create_user(session, provider=provider, identity=identity)
    except OAuthRefused as refused:
        logger.warning(
            "OAuth sign-in refused: provider=%s email=%s reason=%s (%s)",
            provider,
            email,
            refused.code,
            refused,
        )
        await session.rollback()
        return _frontend_error_redirect(refused.code)
    except Exception:
        logger.exception(
            "Error creating/linking OAuth user: provider=%s email=%s", provider, email
        )
        await session.rollback()
        return _frontend_error_redirect("server_error")

    # Keep parity with classic password login: inactive users must not be able
    # to authenticate through OAuth. Superusers never sign in this way either.
    if getattr(user, "is_superuser", False):
        await session.rollback()
        return _frontend_error_redirect("superuser_oauth_disabled")
    if not user.is_active:
        logger.info(
            "OAuth login blocked for inactive user: provider=%s user=%s email=%s",
            provider,
            user.id,
            email,
        )
        await session.rollback()
        return _frontend_error_redirect("user_inactive")

    _access_tok, refresh_tok, refresh_jti, refresh_expires_at = _build_token_bundle(
        user.id
    )
    mark_logged_in(user)
    # create_for_user internally calls CrudBase.create which commits the transaction,
    # flushing the pending user (last_login included) + oauth_link writes alongside
    # the refresh token.
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
    return _frontend_redirect(refresh_tok)
