import hmac
import ipaddress
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import security
from app.core.cache import RedisCache
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import AppError
from app.core.field_visibility import reveal_internal_fields
from app.core.rate_limit import get_client_ip
from app.features.user.models.user import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

optional_reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False
)


async def get_redis_cache() -> AsyncGenerator[Redis, None]:
    """Get redis cache."""
    async with RedisCache() as cache:
        yield cache


SessionDep = Annotated[AsyncSession, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]
RedisDep = Annotated[Redis, Depends(get_redis_cache)]


async def _authenticated_user(session: AsyncSession, token: str) -> User:
    """The user behind a valid access token (no enrolment rule)."""
    try:
        payload = security.decode_token(token)
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        # Expired / malformed access token = authentication failure → 401 so the
        # client's interceptor refreshes (a 403 would leave it stuck until reload).
        raise AppError(
            code="auth.credentials.invalid",
            status_code=401,
            message="Could not validate credentials",
            details={"reason": "invalid_or_malformed_token"},
        )
    if token_data.type != "access":
        raise AppError(
            code="auth.credentials.invalid",
            status_code=401,
            message="Could not validate credentials",
            details={"reason": "invalid_token_type", "token_type": token_data.type},
        )
    user = await session.get(User, token_data.sub)
    if not user:
        raise AppError(
            code="auth.user.not_found",
            status_code=404,
            message="User not found",
            details={"user_id": str(token_data.sub)},
        )
    if not user.is_active:
        raise AppError(
            code="auth.user.inactive",
            status_code=400,
            message="Inactive user",
            details={"user_id": str(user.id)},
        )
    if not token_data.stp or not hmac.compare_digest(
        token_data.stp, user.security_stamp
    ):
        # Password changed, account deactivated, rights changed… since the
        # token was issued: 401, and the refresh token was revoked with it.
        raise AppError(
            code="auth.credentials.invalid",
            status_code=401,
            message="Could not validate credentials",
            details={"reason": "session_revoked"},
        )
    return user


def must_enrol_second_factor(user: User) -> bool:
    """A superuser who must set up 2FA (``ADMIN_2FA_REQUIRED``) and has not."""
    return bool(
        user.is_superuser and settings.admin_2fa_required and not user.totp_enabled
    )


def _enrollment_required(user: User) -> AppError:
    return AppError(
        code="auth.totp.enrollment_required",
        status_code=403,
        message=(
            "La double authentification est obligatoire pour l'administration : "
            "activez-la pour continuer"
        ),
        details={"user_id": str(user.id)},
    )


def _admin_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    raw = (settings.ADMIN_ALLOWED_IPS or "").split()
    return [ipaddress.ip_network(cidr, strict=False) for cidr in raw]


def _check_admin_network(user: User, request: Request | None) -> None:
    """A superuser acts from ``ADMIN_ALLOWED_IPS`` only, on every route."""
    if request is None or not user.is_superuser:
        return
    networks = _admin_networks()
    if not networks:
        return
    try:
        address = ipaddress.ip_address(get_client_ip(request))
    except ValueError:
        address = None
    if address is None or not any(address in net for net in networks):
        raise AppError(
            code="auth.admin.network_denied",
            status_code=403,
            message="Accès réservé : administration depuis un réseau autorisé.",
            details={},
        )


async def get_current_user(
    session: SessionDep,
    token: TokenDep,
    request: Request = None,  # type: ignore[assignment]  # injected by FastAPI
) -> User:
    """The signed-in user.

    A superuser who must enrol in 2FA and has not is refused here, on every
    route (audit 2026-11, S5): the rule was only in ``CurrentSuperUser``, so
    the routes checking ``is_superuser`` by hand (and ``BaseRouter``) still
    granted the admin powers, and the internal fields were revealed before
    any check. Only ``GET /users/me`` and the enrolment endpoints take
    :data:`CurrentUserEnrolling`.
    """
    user = await _authenticated_user(session, token)
    _check_admin_network(user, request)
    if must_enrol_second_factor(user):
        raise _enrollment_required(user)
    if user.is_superuser:
        # Cost, supplier price and margins serialize for this request only.
        reveal_internal_fields()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_enrolling(
    session: SessionDep,
    token: TokenDep,
    request: Request = None,  # type: ignore[assignment]  # injected by FastAPI
) -> User:
    """The signed-in user, 2FA enrolment pending or not — for the profile
    (who is signed in) and the enrolment screens only. Reveals nothing."""
    user = await _authenticated_user(session, token)
    _check_admin_network(user, request)
    return user


CurrentUserEnrolling = Annotated[User, Depends(get_current_user_enrolling)]


async def get_current_verified_user(current_user: CurrentUser) -> User:
    """Get current verified user."""
    if not current_user.is_verified:
        raise AppError(
            code="auth.user.unverified",
            status_code=400,
            message="Unverified user",
            details={"user_id": str(current_user.id)},
        )
    return current_user


CurrentVerifiedUser = Annotated[User, Depends(get_current_verified_user)]


async def get_current_user_optional(
    session: SessionDep, token: str | None = Depends(optional_reusable_oauth2)
) -> CurrentUser | None:
    """Get current user optional."""
    if token is None:
        return None
    try:
        return await get_current_user(session, token)
    except AppError:
        return None


CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


def _require_superuser(user: User) -> User:
    if not user.is_superuser:
        raise AppError(
            code="auth.superuser.required",
            status_code=403,
            message="The user doesn't have enough privileges",
            details={"user_id": str(user.id)},
        )
    return user


async def get_current_active_superuser(current_user: CurrentUser) -> User:
    """Get current active superuser.

    Where two-factor authentication is required (``ADMIN_2FA_REQUIRED``,
    production by default), a superuser who has not set it up is refused
    with ``auth.totp.enrollment_required``: the admin sends them to the
    enrolment screen, the only one they can reach.
    """
    _require_superuser(current_user)
    if must_enrol_second_factor(current_user):
        raise _enrollment_required(current_user)
    return current_user


CurrentSuperUser = Annotated[User, Depends(get_current_active_superuser)]


async def get_current_superuser_enrolling(current_user: CurrentUserEnrolling) -> User:
    """A superuser, two-factor set up or not (the enrolment endpoints)."""
    return _require_superuser(current_user)


CurrentSuperUserEnrolling = Annotated[User, Depends(get_current_superuser_enrolling)]


async def get_current_logistics_admin(
    current_user: CurrentUser, session: SessionDep
) -> User:
    """Gate for the back-office logistics endpoints.

    Superusers always pass. When ``ENABLE_GROUP_PERMISSIONS`` is on, a
    non-superuser also passes if it belongs to a *security* group that grants
    ``can_update`` on ``shipping_route_trackings`` (the ``logistics_admin`` group
    seeded in initial_data). This is an explicit **allow-list**: unlike
    ``CrudBase.check_user_permission`` (deny-list — an ungrouped user passes),
    an ungrouped non-superuser is **denied**. With RBAC disabled, the gate stays
    superuser-only, preserving today's behaviour.
    """
    if current_user.is_superuser:
        return current_user

    from app.core import runtime_settings

    if await runtime_settings.get("enable_group_permissions", session):
        from sqlmodel import col, select

        from app.features.user.models.group import Group
        from app.features.user.models.group_security import GroupSecurity
        from app.features.user.models.user_group import UserGroup

        stmt = (
            select(GroupSecurity)
            .join(Group, col(GroupSecurity.group_id) == col(Group.id))
            .join(UserGroup, col(UserGroup.group_id) == col(Group.id))
            .where(
                UserGroup.user_id == current_user.id,
                Group.group_type == "security",
                GroupSecurity.table_name == "shipping_route_trackings",
                col(GroupSecurity.is_active).is_(True),
                col(GroupSecurity.can_update).is_(True),
            )
            .limit(1)
        )
        result = await session.exec(stmt)
        if result.first() is not None:
            return current_user

    raise AppError(
        code="auth.logistics.required",
        status_code=403,
        message="Accès réservé à la logistique",
        details={"user_id": str(current_user.id)},
    )


CurrentLogisticsAdmin = Annotated[User, Depends(get_current_logistics_admin)]


def module_required(key: str) -> Callable[..., Awaitable[None]]:
    """Dependency: an explicit 404 while the module ``key`` is switched off.

    Used at router level (``dependencies=[Depends(module_required("quotes"))]``)
    for the admin routes of a switchable module (Admin → Modules).
    """
    from app.features.system.modules import require_module, spec_for

    spec_for(key)  # fail at import time on a typo, not at the first request

    async def _gate(session: SessionDep) -> None:
        await require_module(session, key)

    _gate.__name__ = f"module_required_{key}"
    return _gate
