# mypy: disable-error-code="arg-type"

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.inventory.models.stock_movement import (
    InventoryStockMovement,
    InventoryStockMovementCreate,
    InventoryStockMovementUpdate,
    MovementStatus,
    MovementType,
    ReferenceType,
)


class InventoryStockMovementCrud(
    CrudBase[
        InventoryStockMovement,
        InventoryStockMovementCreate,
        InventoryStockMovementUpdate,
    ]
):
    """CRUD operations for InventoryStockMovement"""

    async def get_by_product(
        self,
        session: AsyncSession,
        *,
        product_id: uuid.UUID,
        limit: int = 100,
    ) -> list[InventoryStockMovement]:
        """Get stock movements for a specific product"""
        statement = (
            select(InventoryStockMovement)
            .where(
                InventoryStockMovement.product_id == product_id,
                col(InventoryStockMovement.is_active).is_(True),
            )
            .order_by(col(InventoryStockMovement.created_at).desc())
            .limit(limit)
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_by_reference(
        self,
        session: AsyncSession,
        *,
        reference_type: str,
        reference_id: uuid.UUID,
    ) -> list[InventoryStockMovement]:
        """Get stock movements by reference"""
        statement = select(InventoryStockMovement).where(
            InventoryStockMovement.reference_type == reference_type,
            InventoryStockMovement.reference_id == reference_id,
            col(InventoryStockMovement.is_active).is_(True),
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_stale_order_reference_ids(
        self,
        session: AsyncSession,
        *,
        older_than: datetime,
        limit: int = 500,
        order_status_names: Iterable[str] | None = None,
    ) -> list[uuid.UUID]:
        """Return order ids still holding PENDING outgoing reservations.

        Only movements created strictly before ``older_than`` count, so an
        order being checked out right now is never picked up. Used by the
        reservation sweep: without it, a checkout never followed by a payment
        held its stock forever.

        ``order_status_names``: only orders in these statuses (or vanished
        ones). Filtering here, oldest first, rather than in the caller: 500
        orders the sweep must skip (awaiting a transfer…) no longer fill
        every batch and hide the others for good (audit 2026-11, B7).
        """
        from app.features.order.models.order import Order
        from app.features.order.models.order_status import OrderStatus

        oldest = func.min(col(InventoryStockMovement.created_at))
        statement = (
            select(InventoryStockMovement.reference_id)
            .outerjoin(Order, col(Order.id) == col(InventoryStockMovement.reference_id))
            .outerjoin(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
            .where(
                InventoryStockMovement.reference_type == ReferenceType.ORDER.value,
                InventoryStockMovement.movement_type == MovementType.OUTGOING.value,
                InventoryStockMovement.status == MovementStatus.PENDING.value,
                col(InventoryStockMovement.reference_id).is_not(None),
                col(InventoryStockMovement.created_at) < older_than,
                col(InventoryStockMovement.is_active).is_(True),
            )
            .group_by(col(InventoryStockMovement.reference_id))
            .order_by(oldest)
            .limit(limit)
        )
        if order_status_names is not None:
            statement = statement.where(
                or_(
                    col(Order.id).is_(None),
                    col(OrderStatus.name).in_(list(order_status_names)),
                )
            )
        result = await session.exec(statement)
        return [reference_id for reference_id in result.all() if reference_id]

    async def get_by_place(
        self,
        session: AsyncSession,
        *,
        place_id: uuid.UUID,
        movement_type: str | None = None,
        limit: int = 100,
    ) -> list[InventoryStockMovement]:
        """Get stock movements for a specific place"""
        conditions = [
            (InventoryStockMovement.from_place_id == place_id)
            | (InventoryStockMovement.to_place_id == place_id),
            col(InventoryStockMovement.is_active).is_(True),
        ]

        if movement_type:
            conditions.append(InventoryStockMovement.movement_type == movement_type)

        statement = (
            select(InventoryStockMovement)
            .where(*conditions)
            .order_by(col(InventoryStockMovement.created_at).desc())
            .limit(limit)
        )
        result = await session.exec(statement)
        return list(result.all())


crud_stock_movement = InventoryStockMovementCrud(
    model=InventoryStockMovement,
    schema_create=InventoryStockMovementCreate,
    schema_update=InventoryStockMovementUpdate,
    order_by=col(InventoryStockMovement.created_at).desc(),
    outbox_events={
        "create": "create.stock_movement",
        "update": "update.stock_movement",
        "delete": "delete.stock_movement",
    },
)
