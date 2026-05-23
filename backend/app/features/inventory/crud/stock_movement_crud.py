# mypy: disable-error-code="arg-type"

import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.inventory.models.stock_movement import (
    InventoryStockMovement,
    InventoryStockMovementCreate,
    InventoryStockMovementUpdate,
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
