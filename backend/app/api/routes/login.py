import hmac
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Never

from fastapi import APIRouter, Depends, Form, Request, Response, status
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
from app.core.rate_limit import get_client_ip, hit_rate_limit, rate_limited
from app.features.base.crud import RecordNotFoundError
from app.features.system import audit
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import AccountLockedError, crud_user, mark_logged_in
from app.features.user.models.user import (
    AccessTokenResponse,
    TokenPayload,
)
from app.features.user.services.two_factor import verify_second_factor

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


def _build_token_bundle(
    user_id: uuid.UUID, stamp: str
) -> tuple[str, str, str, datetime]:
    """Build token bundle."""
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_jti = str(uuid.uuid4())
    access_token = security.create_access_token(
        user_id, expires_delta=access_token_expires, stamp=stamp
    )
    refresh_token = security.create_refresh_token(
        user_id,
        expires_delta=refresh_token_expires,
        jti=refresh_jti,
        stamp=stamp,
    )
    refresh_expires_at = datetime.now(UTC) + refresh_token_expires

    return access_token, refresh_token, refresh_jti, refresh_expires_at


@router.post("/login/access-token")
async def login_access_token(
    request: Request,
    response: Response,
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    # Annotated so a direct call (tests) gets a real default, not the marker.
    totp_code: Annotated[
        str | None,
        Form(
            description=(
                "Administrators with two-factor authentication: the code of "
                "their app, or one of their recovery codes"
            )
        ),
    ] = None,
) -> AccessTokenResponse:
    """OAuth2 compatible password login.

    Returns the access token in the body (held in SPA memory) and sets the
    refresh token as an HttpOnly cookie. Per-IP throttled + per-account
    lockout against brute force. A superuser with two-factor authentication
    also sends ``totp_code`` (``login.totp.required`` without it); a wrong
    code counts towards the lockout like a wrong password.
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

    user_agent = request.headers.get("user-agent")
    try:
        user = await crud_user.authenticate(
            session=session,
            email=form_data.username,
            password=form_data.password,
            client_ip=client_ip,
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
        await _audit_failed_admin_login(
            session, form_data.username, ip=client_ip, user_agent=user_agent
        )
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

    second_factor: str | None = None
    if getattr(user, "is_superuser", False) and getattr(user, "totp_enabled", False):
        user_id, user_email = user.id, user.email
        if not (totp_code or "").strip():
            raise AppError(
                code="login.totp.required",
                status_code=401,
                message="Saisissez le code de votre application d'authentification.",
                details={"reason": "totp_required"},
            )
        second_factor = verify_second_factor(user, totp_code)
        if second_factor is None:
            await audit.record(
                event="auth.login.totp_failed",
                actor_id=user_id,
                actor_email=user_email,
                ip=client_ip,
                user_agent=user_agent,
            )
            try:
                await crud_user.register_failed_attempt(
                    session, user, client_ip=client_ip
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
            raise AppError(
                code="login.totp.invalid",
                status_code=401,
                message="Code de vérification incorrect.",
                details={"reason": "totp_invalid"},
            )

    access_token, refresh_token, refresh_jti, refresh_expires_at = _build_token_bundle(
        user.id, user.security_stamp
    )
    is_admin = bool(getattr(user, "is_superuser", False))
    admin_id, admin_email = user.id, getattr(user, "email", None)

    # Trace de connexion : le back-office s'en sert pour distinguer un compte
    # invité jamais ouvert d'un client actif. L'instance est déjà suivie par la
    # session (chargée par authenticate) : le commit de create_for_user juste
    # en dessous persiste la modification.
    mark_logged_in(user)
    await crud_user_refresh_token.create_for_user(
        session=session,
        user_id=user.id,
        jti=refresh_jti,
        expires_at=refresh_expires_at,
        user=user,
    )

    set_refresh_cookie(response, refresh_token)
    if is_admin:
        await audit.record(
            event="auth.login.success",
            actor_id=admin_id,
            actor_email=admin_email,
            details={"second_factor": second_factor} if second_factor else None,
            ip=client_ip,
            user_agent=user_agent,
        )
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # seconds
    )


async def _audit_failed_admin_login(
    session: SessionDep, email: str, *, ip: str | None, user_agent: str | None
) -> None:
    """A wrong password on an administrator account is journaled.

    Best effort: the journal never changes the outcome of a sign-in.
    """
    try:
        admin = await crud_user.get_by_email(session, email=email)
    except Exception:  # noqa: BLE001
        return
    if admin is not None and getattr(admin, "is_superuser", False):
        await audit.record(
            event="auth.login.failed",
            actor_id=admin.id,
            actor_email=admin.email,
            ip=ip,
            user_agent=user_agent,
        )


def _check_admin_origin(request: Request, user: Any) -> None:
    """A superuser's session is refreshed from the back-office only.

    The storefront and the admin share the API and its refresh cookie, and
    CORS lets both call it with credentials: a script injected in the
    storefront could exchange an admin's cookie for an admin access token.
    The browser sets ``Origin`` itself (a page cannot forge it), so the
    exchange is refused from any other origin — without revoking anything,
    the admin's own session goes on (audit 2026-11, S2). A request without
    ``Origin`` does not come from a page script.
    """
    admin_host = (settings.ADMIN_FRONTEND_HOST or "").strip().rstrip("/")
    if not admin_host or not getattr(user, "is_superuser", False):
        return
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin and origin != admin_host:
        raise AppError(
            code="login.refresh_token.admin_origin",
            status_code=403,
            message="Session d'administration : reconnectez-vous depuis l'admin.",
            details={},
        )


@router.post(
    "/login/refresh-token",
    # Generous: the SPA refreshes at every page load, behind shared NAT IPs.
    dependencies=[Depends(rate_limited("refresh", limit=60, window_seconds=60))],
)
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

    if not token_data.stp or not hmac.compare_digest(
        token_data.stp, user.security_stamp
    ):
        # The stamp changed since this session opened (password, 2FA reset or
        # disabled, deactivation): every session of the account is over.
        await crud_user_refresh_token.revoke_all_active_for_user(
            session=session,
            user_id=user_id,
            reason="security_stamp_changed",
        )
        raise AppError(
            code="login.refresh_token.revoked",
            status_code=401,
            message="Refresh token révoqué",
            details={"user_id": str(user_id), "jti": token_jti},
        )

    _check_admin_origin(request, user)

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

    now = datetime.now(UTC)
    # expires_at is timestamptz since sqlmodel 0.0.45; keep the guard for a
    # naive value (always UTC wall-clock) before comparing to the aware `now`.
    session_expires_at = current_refresh_session.expires_at
    if session_expires_at.tzinfo is None:
        session_expires_at = session_expires_at.replace(tzinfo=UTC)

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
        user.id, user.security_stamp
    )

    rotated = await crud_user_refresh_token.rotate_token(
        session=session,
        current_token=current_refresh_session,
        new_jti=refresh_jti,
        new_expires_at=refresh_expires_at,
        user=user,
    )
    if rotated is None:
        # A concurrent refresh used this cookie first: reuse, same as above.
        await crud_user_refresh_token.revoke_all_active_for_user(
            session=session,
            user_id=user_id,
            reason="reuse_detected",
        )
        raise AppError(
            code="login.refresh_token.revoked",
            status_code=401,
            message="Refresh token révoqué",
            details={"user_id": str(user_id), "jti": token_jti},
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
