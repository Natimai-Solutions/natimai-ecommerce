import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Never

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError

from app.api.deps import SessionDep
from app.core import security
from app.core.auth_cookies import (
    clear_refresh_cookie,
    read_refresh_cookie,
    set_refresh_cookie,
)
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import get_client_ip, hit_rate_limit
from app.features.base.crud import RecordNotFoundError
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import AccountLockedError, crud_user
from app.features.user.models.user import (
    AccessTokenResponse,
    TokenPayload,
)

router = APIRouter()


def _raise_invalid_refresh_token(
    *,
    reason: str,
    user_id: uuid.UUID | None = None,
    jti: str | None = None,
) -> Never:
    """Raise a standardized AppError for invalid refresh-token scenarios."""
    details: dict[str, str] = {"reason": reason}
    if user_id is not None:
        details["user_id"] = str(user_id)
    if jti is not None:
        details["jti"] = jti

    raise AppError(
        code="login.refresh_token.invalid",
        status_code=401,
        message="Refresh token invalide",
        details=details,
    )


def _build_token_bundle(user_id: uuid.UUID) -> tuple[str, str, str, datetime]:
    """Build token bundle."""
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_jti = str(uuid.uuid4())
    access_token = security.create_access_token(
        user_id, expires_delta=access_token_expires
    )
    refresh_token = security.create_refresh_token(
        user_id,
        expires_delta=refresh_token_expires,
        jti=refresh_jti,
    )
    refresh_expires_at = datetime.now(timezone.utc) + refresh_token_expires

    return access_token, refresh_token, refresh_jti, refresh_expires_at


@router.post("/login/access-token")
async def login_access_token(
    request: Request,
    response: Response,
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> AccessTokenResponse:
    """OAuth2 compatible password login.

    Returns the access token in the body (held in SPA memory) and sets the
    refresh token as an HttpOnly cookie. Per-IP throttled + per-account
    lockout against brute force.
    """
    client_ip = get_client_ip(request)
    if await hit_rate_limit(
        f"login:ip:{client_ip}",
        limit=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise AppError(
            code="login.rate_limited",
            status_code=429,
            message="Trop de tentatives de connexion. Réessayez dans une minute.",
            details={"retry_after_seconds": settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS},
        )

    try:
        user = await crud_user.authenticate(
            session=session, email=form_data.username, password=form_data.password
        )
    except AccountLockedError as exc:
        raise AppError(
            code="login.account.locked",
            status_code=429,
            message=(
                "Compte temporairement verrouillé après trop de tentatives. "
                "Réessayez plus tard."
            ),
            details={"locked_until": exc.locked_until.isoformat()},
        ) from exc
    if not user:
        raise AppError(
            code="login.credentials.invalid",
            status_code=400,
            message="Email ou mot de passe incorrect.",
            details={"reason": "invalid_credentials"},
        )
    elif not user.is_active:
        raise AppError(
            code="login.user.inactive",
            status_code=400,
            message="Utilisateur désactivé",
            details={"user_id": str(user.id)},
        )

    access_token, refresh_token, refresh_jti, refresh_expires_at = _build_token_bundle(
        user.id
    )

    await crud_user_refresh_token.create_for_user(
        session=session,
        user_id=user.id,
        jti=refresh_jti,
        expires_at=refresh_expires_at,
        user=user,
    )

    set_refresh_cookie(response, refresh_token)
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # seconds
    )


@router.post("/login/refresh-token")
async def refresh_access_token(
    request: Request,
    response: Response,
    session: SessionDep,
) -> AccessTokenResponse:
    """Rotate the refresh token (read from the HttpOnly cookie) and mint a new
    access token. The new refresh token is written back as a cookie."""
    refresh_cookie = read_refresh_cookie(request)
    if not refresh_cookie:
        _raise_invalid_refresh_token(reason="cookie_missing")

    try:
        decoded_payload = security.decode_token(refresh_cookie)
        token_data = TokenPayload(**decoded_payload)
    except (InvalidTokenError, ValidationError):
        _raise_invalid_refresh_token(reason="decode_failed")

    if token_data.type != "refresh" or not token_data.sub or not token_data.jti:
        _raise_invalid_refresh_token(reason="payload_invalid")

    assert token_data.sub is not None
    assert token_data.jti is not None
    token_sub = token_data.sub
    token_jti: str = token_data.jti

    try:
        user_id = uuid.UUID(token_sub)
    except ValueError:
        _raise_invalid_refresh_token(reason="subject_invalid", jti=token_jti)

    try:
        user = await crud_user.read(session=session, id=user_id)
    except RecordNotFoundError:
        _raise_invalid_refresh_token(
            reason="user_not_found",
            user_id=user_id,
            jti=token_jti,
        )

    if not user.is_active:
        raise AppError(
            code="login.user.inactive",
            status_code=400,
            message="Utilisateur désactivé",
            details={"user_id": str(user.id)},
        )

    current_refresh_session = await crud_user_refresh_token.get_by_user_and_jti(
        session=session,
        user_id=user_id,
        jti=token_jti,
    )
    if not current_refresh_session:
        _raise_invalid_refresh_token(
            reason="session_not_found",
            user_id=user_id,
            jti=token_jti,
        )

    now = datetime.now(timezone.utc)
    # expires_at is stored in a naive (tz-less) column but always holds UTC
    # wall-clock — make it aware before comparing to the aware `now`.
    session_expires_at = current_refresh_session.expires_at
    if session_expires_at.tzinfo is None:
        session_expires_at = session_expires_at.replace(tzinfo=timezone.utc)

    if current_refresh_session.revoked_at is not None:
        await crud_user_refresh_token.revoke_all_active_for_user(
            session=session,
            user_id=user_id,
            reason="reuse_detected",
        )
        raise AppError(
            code="login.refresh_token.revoked",
            status_code=401,
            message="Refresh token révoqué",
            details={
                "user_id": str(user_id),
                "jti": token_jti,
            },
        )

    if session_expires_at <= now:
        await crud_user_refresh_token.revoke_token(
            session=session,
            token=current_refresh_session,
            reason="expired",
            user=user,
        )
        raise AppError(
            code="login.refresh_token.expired",
            status_code=401,
            message="Refresh token expiré",
            details={
                "user_id": str(user_id),
                "jti": token_jti,
            },
        )

    access_token, refresh_token, refresh_jti, refresh_expires_at = _build_token_bundle(
        user.id
    )

    await crud_user_refresh_token.rotate_token(
        session=session,
        current_token=current_refresh_session,
        new_jti=refresh_jti,
        new_expires_at=refresh_expires_at,
        user=user,
    )

    set_refresh_cookie(response, refresh_token)
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
) -> Response:
    """Revoke the current refresh-token session and clear the cookie.

    Idempotent: always clears the cookie and returns 204, even if the cookie is
    missing or already invalid.
    """
    refresh_cookie = read_refresh_cookie(request)
    if refresh_cookie:
        try:
            decoded = security.decode_token(refresh_cookie)
            token_data = TokenPayload(**decoded)
            if token_data.type == "refresh" and token_data.sub and token_data.jti:
                user_id = uuid.UUID(token_data.sub)
                token_row = await crud_user_refresh_token.get_by_user_and_jti(
                    session=session, user_id=user_id, jti=token_data.jti
                )
                if token_row is not None and token_row.revoked_at is None:
                    await crud_user_refresh_token.revoke_token(
                        session=session, token=token_row, reason="logout"
                    )
        except (InvalidTokenError, ValidationError, ValueError):
            # Malformed/expired cookie — nothing to revoke, just clear it.
            pass

    clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
