from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.product.models.brand import Brand, BrandCreate, BrandUpdate


class BrandCrud(CrudBase[Brand, BrandCreate, BrandUpdate]):
    async def get_by_name(self, session: AsyncSession, name: str) -> Brand | None:
        """Récupère une marque par son nom"""
        statement = select(Brand).where(
            Brand.name == name,
            Brand.is_active.is_(True),
        )
        result = await session.exec(statement)
        return result.first()


crud_brand = BrandCrud(
    model=Brand,
    schema_create=BrandCreate,
    schema_update=BrandUpdate,
    order_by=Brand.name,
    outbox_events={
        "create": "create.brand",
        "update": "update.brand",
        "delete": "delete.brand",
    },
)
