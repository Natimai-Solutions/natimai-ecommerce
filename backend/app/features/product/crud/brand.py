from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.product.models.brand import Brand, BrandCreate, BrandUpdate


class BrandCrud(CrudBase[Brand, BrandCreate, BrandUpdate]):
    """Represents brand crud."""

    async def get_by_name(self, session: AsyncSession, name: str) -> Brand | None:
        """Get by name."""
        statement = select(Brand).where(
            Brand.name == name,
            col(Brand.is_active).is_(True),
        )
        result = await session.exec(statement)
        return result.first()


crud_brand = BrandCrud(
    model=Brand,
    schema_create=BrandCreate,
    schema_update=BrandUpdate,
    order_by=col(Brand.name),
    outbox_events={
        "create": "create.brand",
        "update": "update.brand",
        "delete": "delete.brand",
    },
)
