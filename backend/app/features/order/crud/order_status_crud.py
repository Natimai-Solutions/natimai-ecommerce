from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.order.models.order_status import (
    OrderStatus,
    OrderStatusCreate,
    OrderStatusUpdate,
)


class OrderStatusCrud(CrudBase[OrderStatus, OrderStatusCreate, OrderStatusUpdate]):
    async def get_by_name(self, session: AsyncSession, name: str) -> OrderStatus | None:
        """Récupère un statut par son nom"""
        statement = select(OrderStatus).where(
            OrderStatus.name == name,
            col(OrderStatus.is_active).is_(True),
        )
        result = await session.exec(statement)
        return result.first()


crud_order_status = OrderStatusCrud(
    model=OrderStatus,
    schema_create=OrderStatusCreate,
    schema_update=OrderStatusUpdate,
    order_by=col(OrderStatus.created_at).desc(),
    outbox_events={
        "create": "create.order_status",
        "update": "update.order_status",
        "delete": "delete.order_status",
    },
)
