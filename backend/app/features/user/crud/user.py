import uuid
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import verify_password
from app.features.base.crud import CrudBase
from app.features.user.models.user import User, UserCreate, UserUpdate


class CrudUser(CrudBase[User, UserCreate, UserUpdate]):
    async def create(
        self,
        session: AsyncSession,
        *,
        data: UserCreate,
        user: User | None,
    ) -> User:
        """
        Create new user with automatic password hashing.

        The UserCreate model automatically converts 'password' to 'hashed_password'.
        """
        return await super().create(session, data=data, user=user)

    async def update(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        data: UserUpdate | dict[str, Any],
        user: User | None = None,
        record: User | None = None,
    ) -> User:
        """
        Update user with automatic password hashing if password is provided.

        The UserUpdate model automatically converts 'password' to 'hashed_password'.
        """
        return await super().update(
            session,
            id=id,
            data=data,
            user=user,
            record=record,
        )

    async def authenticate(
        self, session: AsyncSession, *, email: str, password: str
    ) -> User | None:
        """
        Authenticate user by email and password.
        """
        stmt = select(User).where(User.email == email)
        result = await session.exec(stmt)
        user = result.first()

        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def get_by_email(self, session: AsyncSession, *, email: str) -> User | None:
        """
        Get user by email address.
        """
        stmt = select(User).where(User.email == email)
        result = await session.exec(stmt)
        return result.first()

    async def is_active(self, user: User) -> bool:
        """
        Check if user is active.
        """
        return user.is_active

    async def is_superuser(self, user: User) -> bool:
        """
        Check if user is superuser.
        """
        return user.is_superuser


crud_user = CrudUser(
    model=User,
    schema_create=UserCreate,
    schema_update=UserUpdate,
    order_by=User.id,
)
