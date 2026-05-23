from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.product.models.category import (
    Category,
    CategoryCreate,
    CategoryUpdate,
)


class CategoryCrud(CrudBase[Category, CategoryCreate, CategoryUpdate]):
    """Represents category crud."""

    async def get_by_name(self, session: AsyncSession, name: str) -> Category | None:
        """Get by name."""
        statement = select(Category).where(
            Category.name == name,
            col(Category.is_active).is_(True),
        )
        result = await session.exec(statement)
        return result.first()


crud_category = CategoryCrud(
    model=Category,
    schema_create=CategoryCreate,
    schema_update=CategoryUpdate,
    order_by=col(Category.name),
    outbox_events={
        "create": "create.category",
        "update": "update.category",
        "delete": "delete.category",
    },
)
