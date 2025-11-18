import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.inventory.models.inventory import (
    Inventory,
    InventoryCreate,
    InventoryUpdate,
)


class InventoryCrud(CrudBase[Inventory, InventoryCreate, InventoryUpdate]):
    """CRUD operations for Inventory"""

    async def get_by_product_and_place(
        self,
        session: AsyncSession,
        *,
        product_id: uuid.UUID,
        place_id: uuid.UUID | None = None,
    ) -> Inventory | None:
        """Get inventory by product and place"""
        conditions = [
            Inventory.product_id == product_id,
            Inventory.is_active.is_(True),
        ]

        if place_id is not None:
            conditions.append(Inventory.place_id == place_id)
        else:
            conditions.append(Inventory.place_id.is_(None))

        statement = select(Inventory).where(*conditions)
        result = await session.exec(statement)
        return result.first()

    async def get_by_product(
        self, session: AsyncSession, *, product_id: uuid.UUID
    ) -> list[Inventory]:
        """Get all inventory records for a product across all places"""
        statement = select(Inventory).where(
            Inventory.product_id == product_id, Inventory.is_active.is_(True)
        )
        result = await session.exec(statement)
        return list(result.all())


crud_inventory = InventoryCrud(
    model=Inventory,
    schema_create=InventoryCreate,
    schema_update=InventoryUpdate,
    order_by=Inventory.created_at,
    outbox_events={
        "create": "create.inventory",
        "update": "update.inventory",
        "delete": "delete.inventory",
    },
)
