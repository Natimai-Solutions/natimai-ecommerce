import uuid
from decimal import Decimal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.order.models.order_line import (
    OrderLine,
    OrderLineCreate,
    OrderLineUpdate,
)


class OrderLineCrud(CrudBase[OrderLine, OrderLineCreate, OrderLineUpdate]):
    async def get_by_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[OrderLine]:
        """Récupère toutes les lignes d'une commande"""
        statement = select(OrderLine).where(
            OrderLine.order_id == order_id,
            col(OrderLine.is_active).is_(True),
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_by_product(
        self,
        session: AsyncSession,
        product_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[OrderLine]:
        """Récupère les lignes de commande pour un produit spécifique"""
        statement = (
            select(OrderLine)
            .where(
                OrderLine.product_id == product_id,
                col(OrderLine.is_active).is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(col(OrderLine.created_at).desc())
        )
        result = await session.exec(statement)
        return list(result.all())

    async def calculate_order_total(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> Decimal:
        """Calcule le total d'une commande à partir de ses lignes"""
        lines = await self.get_by_order(session, order_id)
        total = sum(
            (
                (line.unit_price * line.quantity) - line.discount_amount
                for line in lines
            ),
            Decimal("0.00"),
        )
        return total


crud_order_line = OrderLineCrud(
    model=OrderLine,
    schema_create=OrderLineCreate,
    schema_update=OrderLineUpdate,
    order_by=col(OrderLine.created_at).desc(),
    outbox_events={
        "create": "create.order_line",
        "update": "update.order_line",
        "delete": "delete.order_line",
    },
)
