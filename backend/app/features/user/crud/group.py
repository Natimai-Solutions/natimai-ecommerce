from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase, track_crud_operation
from app.features.user.models.group import Group, GroupCreate, GroupUpdate
from app.features.user.models.user import User


class GroupCrud(CrudBase[Group, GroupCreate, GroupUpdate]):
    """CRUD operations for Group model"""

    @track_crud_operation
    async def get_by_name(
        self,
        session: AsyncSession,
        *,
        name: str,
    ) -> Group | None:
        """
        Get a group by its unique name.

        Args:
            session: Database session
            name: Group name

        Returns:
            Group if found, None otherwise
        """
        statement = select(Group).where(
            Group.name == name,
            Group.is_active.is_(True),
        )
        result = await session.exec(statement)
        return result.first()

    @track_crud_operation
    async def get_by_type(
        self,
        session: AsyncSession,
        *,
        group_type: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Group]:
        """
        Get all groups of a specific type.

        Args:
            session: Database session
            group_type: Type of group ('security', 'pricing', 'discount', 'general')
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of groups matching the type
        """
        statement = (
            select(Group)
            .where(
                Group.group_type == group_type,
                Group.is_active.is_(True),
            )
            .order_by(Group.priority.desc(), Group.name)
            .offset(skip)
            .limit(limit)
        )
        result = await session.exec(statement)
        return list(result.all())

    @track_crud_operation
    async def get_pricing_groups(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Group]:
        """
        Get all pricing/discount groups ordered by priority.

        Args:
            session: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of pricing groups with discount_percentage set
        """
        statement = (
            select(Group)
            .where(
                Group.discount_percentage.is_not(None),
                Group.is_active.is_(True),
            )
            .order_by(Group.priority.desc(), Group.discount_percentage.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.exec(statement)
        return list(result.all())

    @track_crud_operation
    async def before_create(
        self,
        session: AsyncSession,
        *,
        data: GroupCreate,
        user: User | None,
    ) -> None:
        """
        Validation before creating a group.

        Args:
            session: Database session
            data: Group creation data
            user: User creating the group

        Raises:
            ValueError: If group name already exists
        """
        existing = await self.get_by_name(session, name=data.name)
        if existing:
            raise ValueError(f"Group with name '{data.name}' already exists")


# Singleton instance
crud_group = GroupCrud(
    model=Group,
    schema_create=GroupCreate,
    schema_update=GroupUpdate,
    order_by=Group.priority.desc(),
    outbox_events={
        "create": "create.group",
        "update": "update.group",
        "delete": "delete.group",
    },
)
