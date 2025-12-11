import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.order.models.order_status import (
    OrderStatus,
    OrderStatusCreate,
    OrderStatusUpdate,
)


class OrderStatusCrud(CrudBase[OrderStatus, OrderStatusCreate, OrderStatusUpdate]):
    async def get_by_name(
        self, session: AsyncSession, name: str
    ) -> OrderStatus | None:
        """Récupère un statut par son nom"""
        statement = select(OrderStatus).where(
            OrderStatus.name == name,
            OrderStatus.is_active.is_(True),
        )
        result = await session.exec(statement)
        return result.first()

    async def get_by_code(
        self, session: AsyncSession, code: str
    ) -> OrderStatus | None:
        """Récupère un statut par son code"""
        statement = select(OrderStatus).where(
            OrderStatus.code == code,
            OrderStatus.is_active.is_(True),
        )
        result = await session.exec(statement)
        return result.first()

    async def get_ordered(
        self, session: AsyncSession
    ) -> list[OrderStatus]:
        """Récupère tous les statuts ordonnés par sequence"""
        statement = (
            select(OrderStatus)
            .where(OrderStatus.is_active.is_(True))
            .order_by(OrderStatus.sequence)
        )
        result = await session.exec(statement)
        return list(result.all())


crud_order_status = OrderStatusCrud(
    model=OrderStatus,
    schema_create=OrderStatusCreate,
    schema_update=OrderStatusUpdate,
    order_by=OrderStatus.created_at.desc(),
    outbox_events={
        "create": "create.order_status",
        "update": "update.order_status",
        "delete": "delete.order_status",
    },
)
