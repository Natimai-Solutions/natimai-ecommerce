import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.order.models.order import Order, OrderCreate, OrderUpdate


class OrderCrud(CrudBase[Order, OrderCreate, OrderUpdate]):
    async def get_by_user(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Order]:
        """Récupère les commandes d'un utilisateur"""
        statement = (
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(Order.created_at.desc())
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_by_status(
        self,
        session: AsyncSession,
        order_status_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Order]:
        """Récupère les commandes par statut"""
        statement = (
            select(Order)
            .where(
                Order.order_status_id == order_status_id,
                Order.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(Order.created_at.desc())
        )
        result = await session.exec(statement)
        return list(result.all())


crud_order = OrderCrud(
    model=Order,
    schema_create=OrderCreate,
    schema_update=OrderUpdate,
    order_by=Order.created_at.desc(),
    outbox_events={
        "create": "create.order",
        "update": "update.order",
        "delete": "delete.order",
    },
)
