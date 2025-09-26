from collections.abc import AsyncGenerator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import security
from app.core.cache import RedisCache
from app.core.config import settings
from app.core.db import get_db
from app.features.user.models.user import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

optional_reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False
)


async def get_redis_cache() -> AsyncGenerator[Redis, None]:
    async with RedisCache() as cache:
        yield cache


SessionDep = Annotated[AsyncSession, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]
RedisDep = Annotated[Redis, Depends(get_redis_cache)]


async def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = await session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_verified_user(current_user: CurrentUser) -> User:
    if not current_user.is_verified:
        raise HTTPException(status_code=400, detail="Unverified user")
    return current_user


CurrentVerifiedUser = Annotated[User, Depends(get_current_verified_user)]


async def get_current_user_optional(
    session: SessionDep, token: str | None = Depends(optional_reusable_oauth2)
) -> CurrentUser | None:
    if token is None:
        return None
    try:
        return await get_current_user(session, token)
    except HTTPException:
        return None


CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


async def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
