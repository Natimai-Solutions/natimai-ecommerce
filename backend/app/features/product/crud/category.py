import uuid

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

    async def get_by_name_ilike(
        self, session: AsyncSession, name: str
    ) -> Category | None:
        """Case-insensitive lookup by name."""
        statement = select(Category).where(
            col(Category.name).ilike(name),
            col(Category.is_active).is_(True),
        )
        result = await session.exec(statement)
        return result.first()

    async def get_by_name_ilike_any(
        self, session: AsyncSession, name: str
    ) -> Category | None:
        """Case-insensitive lookup by name, inactive rows included."""
        statement = select(Category).where(col(Category.name).ilike(name))
        result = await session.exec(statement)
        return result.first()

    async def resolve_merged(
        self, session: AsyncSession, category: Category
    ) -> Category:
        """Follow ``merged_into_id`` to the surviving category (A12).

        A merged category keeps its row so its supplier name still resolves;
        chains are followed (A merged into B, then B into C), with a guard
        against a cycle that a bug could have written.
        """
        seen = {category.id}
        while category.merged_into_id is not None:
            target = await session.get(Category, category.merged_into_id)
            if target is None or target.id in seen:
                break
            seen.add(target.id)
            category = target
        return category

    async def get_or_create_by_name(
        self, session: AsyncSession, *, name: str
    ) -> tuple[Category, bool]:
        """Return (category, created) — create with is_active=True if not found.

        Uses case-insensitive match so 'Ordinateur Portable' and 'ORDINATEUR PORTABLE'
        resolve to the same category. The caller must flush/commit.

        Inactive rows count as found: a category an admin merged (A12) or hid
        must keep absorbing its supplier name, otherwise every sync would
        recreate an active duplicate next to it.
        """
        existing = await self.get_by_name_ilike_any(session, name)
        if existing is not None:
            return await self.resolve_merged(session, existing), False

        category = Category(
            id=uuid.uuid4(),
            name=name,
            is_active=True,
            is_admin_active=True,
        )
        session.add(category)
        await session.flush()
        return category, True


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
