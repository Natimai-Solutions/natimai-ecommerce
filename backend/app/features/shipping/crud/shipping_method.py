from sqlmodel import and_, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.shipping_method import (
    ShippingMethod,
    ShippingMethodCreate,
    ShippingMethodUpdate,
)


class ShippingMethodCrud(
    CrudBase[ShippingMethod, ShippingMethodCreate, ShippingMethodUpdate]
):
    async def get_random_shipping_methods(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[ShippingMethod]:
        statement = (
            select(ShippingMethod)
            .where(
                ShippingMethod.is_admin_active.is_(True),
                ShippingMethod.is_active.is_(True),
            )
            .order_by(func.random())
        )

        if limit > 0:
            statement = statement.limit(limit)

        result = await session.exec(statement)

        return result.all()


crud_shipping_method = ShippingMethodCrud(
    model=ShippingMethod,
    schema_create=ShippingMethodCreate,
    schema_update=ShippingMethodUpdate,
    default_filter=and_(
        ShippingMethod.is_admin_active.is_(True),
    ),
    order_by=ShippingMethod.name,
)
