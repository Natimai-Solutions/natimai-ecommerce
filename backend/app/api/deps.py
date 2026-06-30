from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
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


async def get_current_user(session: SessionDep, token: TokenDep) -> User:
    """Get current user."""
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
    if token_data.type not in (None, "access"):
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
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


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


async def get_current_active_superuser(current_user: CurrentUser) -> User:
    """Get current active superuser."""
    if not current_user.is_superuser:
        raise AppError(
            code="auth.superuser.required",
            status_code=403,
            message="The user doesn't have enough privileges",
            details={"user_id": str(current_user.id)},
        )
    return current_user


CurrentSuperUser = Annotated[User, Depends(get_current_active_superuser)]


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

    if settings.ENABLE_GROUP_PERMISSIONS:
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
