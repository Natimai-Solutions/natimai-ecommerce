from sqlmodel import and_, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.shipping_zone import (
    ShippingZone,
    ShippingZoneCreate,
    ShippingZoneUpdate,
)


class ShippingZoneCrud(CrudBase[ShippingZone, ShippingZoneCreate, ShippingZoneUpdate]):
    async def get_random_shipping_zones(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[ShippingZone]:
        statement = (
            select(ShippingZone)
            .where(
                ShippingZone.is_admin_active.is_(True),
                ShippingZone.is_active.is_(True),
            )
            .order_by(func.random())
        )

        if limit > 0:
            statement = statement.limit(limit)

        result = await session.exec(statement)

        return result.all()


crud_shipping_zone = ShippingZoneCrud(
    model=ShippingZone,
    schema_create=ShippingZoneCreate,
    schema_update=ShippingZoneUpdate,
    default_filter=and_(
        ShippingZone.is_admin_active.is_(True),
    ),
    order_by=ShippingZone.name,
)
