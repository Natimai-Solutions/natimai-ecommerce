from sqlmodel import and_, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.domain.base_crud import CrudBase

from ..models.shipping_status import (
    ShippingStatus,
    ShippingStatusCreate,
    ShippingStatusUpdate,
)

class ShippingStatusCrud(CrudBase[ShippingStatus, ShippingStatusCreate, ShippingStatusUpdate]):
    async def get_random_shipping_statuses(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[ShippingStatus]:
            statement = (
                select(ShippingStatus)
                .where(
                    ShippingStatus.is_admin_active.is_(True),
                    ShippingStatus.is_active.is_(True),
                )
                .order_by(func.random())
            )

            if limit > 0:
                statement = statement.limit(limit)

            result = await session.exec(statement)

            return result.all()
    
crud_shipping_status = ShippingStatusCrud(
     model=ShippingStatus,
     schema_create=ShippingStatusCreate,
     schema_update=ShippingStatusUpdate,
     default_filter=and_(
         ShippingStatus.is_admin_active.is_(True),
     ),
     order_by=ShippingStatus.status,
)