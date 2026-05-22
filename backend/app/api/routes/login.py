import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError

from app.api.deps import SessionDep
from app.core import security
from app.core.config import settings
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import crud_user
from app.features.user.models.user import (
    RefreshTokenRequest,
    Token,
    TokenPayload,
)

router = APIRouter()


def _raise_invalid_refresh_token(
    *,
    reason: str,
    user_id: uuid.UUID | None = None,
    jti: str | None = None,
) -> None:
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
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 compatible token login, get an access token and refresh token for future requests
    """
    user = await crud_user.authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
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

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
    )


@router.post("/login/refresh-token")
async def refresh_access_token(
    session: SessionDep,
    payload: RefreshTokenRequest,
) -> Token:
    """Execute refresh access token."""
    try:
        decoded_payload = security.decode_token(payload.refresh_token)
        token_data = TokenPayload(**decoded_payload)
    except (InvalidTokenError, ValidationError):
        _raise_invalid_refresh_token(reason="decode_failed")

    if token_data.type != "refresh" or not token_data.sub or not token_data.jti:
        _raise_invalid_refresh_token(reason="payload_invalid")

    token_sub = token_data.sub
    token_jti = token_data.jti

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

    if current_refresh_session.expires_at <= now:
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

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
