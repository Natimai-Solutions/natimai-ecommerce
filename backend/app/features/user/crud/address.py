import uuid

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.user.models.address import Address, AddressCreate, AddressUpdate


class AddressCrud(CrudBase[Address, AddressCreate, AddressUpdate]):
    """Represents address crud."""

    async def get_by_user_id(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Address]:
        """Get by user id."""
        statement = (
            select(self.model)
            .where(
                self.model.user_id == user_id,
                col(self.model.is_admin_active).is_(True),
                col(self.model.is_active).is_(True),
            )
            .offset(skip)
            .limit(limit)
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def get_by_user_and_type(
        self, session: AsyncSession, *, user_id: uuid.UUID, address_type: str
    ) -> list[Address]:
        """Get by user and type."""
        statement = select(self.model).where(
            self.model.user_id == user_id,
            self.model.type == address_type,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def create_for_user(
        self,
        session: AsyncSession,
        *,
        data: AddressCreate,
        user_id: uuid.UUID,
        current_user: uuid.UUID | None = None,
    ) -> Address:
        """Create an address for a specific user."""
        obj_data = data.model_dump()
        obj_data["user_id"] = (
            user_id  # Override user_id to ensure it matches the URL parameter
        )
        if current_user:
            obj_data["created_by_id"] = current_user
        record = self.model(**obj_data)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def list_all(
        self,
        session: AsyncSession,
        *,
        validated: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Address]:
        """List addresses across all users (admin), newest first.

        ``validated`` filters on the admin-validation flag when provided.
        """
        statement = select(self.model).where(
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        if validated is not None:
            statement = statement.where(col(self.model.is_validated).is_(validated))
        statement = (
            statement.order_by(col(self.model.created_at).desc())
            .offset(skip)
            .limit(limit)
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def count_all(
        self,
        session: AsyncSession,
        *,
        validated: bool | None = None,
    ) -> int:
        """Count addresses across all users (admin), matching ``list_all`` filters."""
        statement = (
            select(func.count())
            .select_from(self.model)
            .where(
                col(self.model.is_admin_active).is_(True),
                col(self.model.is_active).is_(True),
            )
        )
        if validated is not None:
            statement = statement.where(col(self.model.is_validated).is_(validated))
        result = await session.exec(statement)
        return int(result.one())

    async def validate_address(
        self,
        session: AsyncSession,
        *,
        address: Address,
    ) -> Address:
        """Mark an address as admin-validated."""
        address.is_validated = True
        session.add(address)
        await session.commit()
        await session.refresh(address)
        return address

    async def count_by_user(self, session: AsyncSession, *, user_id: uuid.UUID) -> int:
        """Execute count by user."""
        statement = select(self.model).where(
            self.model.user_id == user_id,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return len(exec_result.all())


crud_address = AddressCrud(
    model=Address,
    schema_create=AddressCreate,
    schema_update=AddressUpdate,
    order_by=Address.created_at,
)
