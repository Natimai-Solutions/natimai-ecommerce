import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import track_crud_operation
from app.features.user.models.user_group import UserGroup


class UserGroupCrud:
    """CRUD operations for UserGroup association"""

    @track_crud_operation
    async def add_user_to_group(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
    ) -> UserGroup:
        """
        Add a user to a group.

        Args:
            session: Database session
            user_id: User ID
            group_id: Group ID

        Returns:
            UserGroup association

        Raises:
            ValueError: If association already exists
        """
        # Check if already exists
        existing = await self.get_user_group(
            session,
            user_id=user_id,
            group_id=group_id,
        )
        if existing:
            raise ValueError(f"User {user_id} is already in group {group_id}")

        # Create association
        user_group = UserGroup(user_id=user_id, group_id=group_id)
        session.add(user_group)
        await session.commit()
        await session.refresh(user_group)
        return user_group

    @track_crud_operation
    async def remove_user_from_group(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
    ) -> bool:
        """
        Remove a user from a group.

        Args:
            session: Database session
            user_id: User ID
            group_id: Group ID

        Returns:
            True if removed, False if not found
        """
        statement = select(UserGroup).where(
            UserGroup.user_id == user_id,
            UserGroup.group_id == group_id,
        )
        result = await session.exec(statement)
        user_group = result.first()

        if not user_group:
            return False

        await session.delete(user_group)
        await session.commit()
        return True

    @track_crud_operation
    async def get_user_group(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
    ) -> UserGroup | None:
        """
        Get a specific user-group association.

        Args:
            session: Database session
            user_id: User ID
            group_id: Group ID

        Returns:
            UserGroup if found, None otherwise
        """
        statement = select(UserGroup).where(
            UserGroup.user_id == user_id,
            UserGroup.group_id == group_id,
        )
        result = await session.exec(statement)
        return result.first()

    @track_crud_operation
    async def get_user_groups(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> list[UserGroup]:
        """
        Get all groups a user belongs to.

        Args:
            session: Database session
            user_id: User ID

        Returns:
            List of UserGroup associations
        """
        statement = select(UserGroup).where(UserGroup.user_id == user_id)
        result = await session.exec(statement)
        return list(result.all())

    @track_crud_operation
    async def get_group_users(
        self,
        session: AsyncSession,
        *,
        group_id: uuid.UUID,
    ) -> list[UserGroup]:
        """
        Get all users in a specific group.

        Args:
            session: Database session
            group_id: Group ID

        Returns:
            List of UserGroup associations
        """
        statement = select(UserGroup).where(UserGroup.group_id == group_id)
        result = await session.exec(statement)
        return list(result.all())

    @track_crud_operation
    async def is_user_in_group(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
    ) -> bool:
        """
        Check if a user is in a specific group.

        Args:
            session: Database session
            user_id: User ID
            group_id: Group ID

        Returns:
            True if user is in group, False otherwise
        """
        user_group = await self.get_user_group(
            session,
            user_id=user_id,
            group_id=group_id,
        )
        return user_group is not None


# Singleton instance
crud_user_group = UserGroupCrud()
