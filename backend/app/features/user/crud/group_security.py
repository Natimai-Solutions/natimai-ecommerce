import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase, track_crud_operation
from app.features.user.models.group_security import (
    GroupSecurity,
    GroupSecurityCreate,
    GroupSecurityUpdate,
)
from app.features.user.models.user import User


class GroupSecurityCrud(
    CrudBase[GroupSecurity, GroupSecurityCreate, GroupSecurityUpdate]
):
    """CRUD operations for GroupSecurity model"""

    @track_crud_operation
    async def get_by_group_and_table(
        self,
        session: AsyncSession,
        *,
        group_id: uuid.UUID,
        table_name: str,
    ) -> GroupSecurity | None:
        """
        Get a security rule for a specific group and table.

        Args:
            session: Database session
            group_id: Group ID
            table_name: Name of the table

        Returns:
            GroupSecurity if found, None otherwise
        """
        statement = select(GroupSecurity).where(
            GroupSecurity.group_id == group_id,
            GroupSecurity.table_name == table_name,
            col(GroupSecurity.is_active).is_(True),
        )
        result = await session.exec(statement)
        return result.first()

    @track_crud_operation
    async def get_group_permissions(
        self,
        session: AsyncSession,
        *,
        group_id: uuid.UUID,
    ) -> list[GroupSecurity]:
        """
        Get all security rules for a specific group.

        Args:
            session: Database session
            group_id: Group ID

        Returns:
            List of security rules for the group
        """
        statement = (
            select(GroupSecurity)
            .where(
                GroupSecurity.group_id == group_id,
                col(GroupSecurity.is_active).is_(True),
            )
            .order_by(col(GroupSecurity.table_name))
        )
        result = await session.exec(statement)
        return list(result.all())

    @track_crud_operation
    async def get_table_permissions(
        self,
        session: AsyncSession,
        *,
        table_name: str,
    ) -> list[GroupSecurity]:
        """
        Get all security rules for a specific table across all groups.

        Args:
            session: Database session
            table_name: Name of the table

        Returns:
            List of security rules for the table
        """
        statement = (
            select(GroupSecurity)
            .where(
                GroupSecurity.table_name == table_name,
                col(GroupSecurity.is_active).is_(True),
            )
            .order_by(col(GroupSecurity.group_id))
        )
        result = await session.exec(statement)
        return list(result.all())

    @track_crud_operation
    async def check_permission(
        self,
        session: AsyncSession,
        *,
        group_id: uuid.UUID,
        table_name: str,
        permission: str,
    ) -> bool:
        """
        Check if a group has a specific permission on a table.

        Args:
            session: Database session
            group_id: Group ID
            table_name: Name of the table
            permission: Permission to check ('read', 'create', 'update', 'delete')

        Returns:
            True if permission is granted, False otherwise
        """
        rule = await self.get_by_group_and_table(
            session,
            group_id=group_id,
            table_name=table_name,
        )

        if not rule:
            return False

        permission_map = {
            "read": rule.can_read,
            "create": rule.can_create,
            "update": rule.can_update,
            "delete": rule.can_delete,
        }

        return bool(permission_map.get(permission, False))

    @track_crud_operation
    async def before_create(
        self,
        session: AsyncSession,
        *,
        data: GroupSecurityCreate,
        user: User | None,
    ) -> None:
        """
        Validation before creating a security rule.

        Args:
            session: Database session
            data: Security rule creation data
            user: User creating the rule

        Raises:
            ValueError: If rule already exists for this group and table
        """
        existing = await self.get_by_group_and_table(
            session,
            group_id=data.group_id,
            table_name=data.table_name,
        )
        if existing:
            raise ValueError(
                f"Security rule already exists for group {data.group_id} "
                f"and table '{data.table_name}'"
            )


# Singleton instance
crud_group_security = GroupSecurityCrud(
    model=GroupSecurity,
    schema_create=GroupSecurityCreate,
    schema_update=GroupSecurityUpdate,
    order_by=col(GroupSecurity.table_name),
    outbox_events={
        "create": "create.group_security",
        "update": "update.group_security",
        "delete": "delete.group_security",
    },
)
