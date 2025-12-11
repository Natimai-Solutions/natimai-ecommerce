import uuid
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase, CrudOperationError
from app.features.order.models.order import Order, OrderCreate, OrderUpdate
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry


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

    async def change_status(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        new_status_id: uuid.UUID,
        user: User | None = None,
    ) -> Order:
        """Change le statut d'une commande et publie un événement outbox"""
        from app.features.order.crud.order_status_crud import crud_order_status

        order = await self.read(session, id=order_id)
        if not order:
            raise CrudOperationError(f"Order {order_id} not found")

        old_status = await crud_order_status.read(session, id=order.order_status_id)
        new_status = await crud_order_status.read(session, id=new_status_id)

        if not new_status:
            raise CrudOperationError(f"Status {new_status_id} not found")

        if old_status and old_status.is_final:
            raise CrudOperationError(
                f"Cannot change status from final state: {old_status.name}"
            )

        old_status_code = old_status.code if old_status else None
        order.order_status_id = new_status_id
        order.modify_at = datetime.now(timezone.utc)
        if user:
            order.modify_by_id = user.id

        session.add(order)
        await session.flush()

        await outbox_registry.publish(
            session,
            event_type="change.order.status",
            payload={
                "order_id": str(order.id),
                "old_status_id": str(old_status.id) if old_status else None,
                "old_status_code": old_status_code,
                "new_status_id": str(new_status.id),
                "new_status_code": new_status.code,
                "user_id": str(order.user_id),
                "changed_by_user_id": str(user.id) if user else None,
            },
        )

        await session.commit()
        await session.refresh(order)

        return order


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
