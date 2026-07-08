"""Admin inventory endpoints (logistics admin).

The raw ``/inventory`` CRUD stays superuser-only and generic; this router
serves the back-office screen: a product-centric stock view and a guarded
adjustment operation that always leaves an audit trail (stock movement).

Model split (owner decision, 08/07/2026):
- ``product.supplier_quantity`` — supplier availability, refreshed by the
  supplier sync, **never** hand-edited here (read-only in the screen);
- ``Inventory`` rows — units physically held in the local warehouse. Empty
  for pure dropship products; used for own products and for the hybrid case
  (supplier-synced products bought ahead and stored locally — the checkout
  already consumes local stock first, then supplier stock).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlmodel import col, func, or_, select

from app.api.deps import CurrentLogisticsAdmin, SessionDep
from app.core.errors import AppError
from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.inventory.models.inventory import Inventory, InventoryCreate
from app.features.inventory.models.stock_movement import (
    InventoryStockMovementCreate,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.product.models.product import Product

router = APIRouter(prefix="/admin/inventory", tags=["admin-inventory"])


class AdminInventoryItem(BaseModel):
    """A product with its local stock and (read-only) supplier availability."""

    product_id: uuid.UUID
    product_name: str
    is_supplier_managed: bool
    supplier_name: str | None = None
    supplier_quantity: Decimal
    local_quantity: Decimal
    inventory_id: uuid.UUID | None = None
    place_id: uuid.UUID | None = None


class AdminInventoryList(BaseModel):
    """Paginated inventory listing."""

    data: list[AdminInventoryItem]
    count: int


class InventoryAdjustRequest(BaseModel):
    """Set the local stock of a product to an absolute quantity."""

    product_id: uuid.UUID
    place_id: uuid.UUID | None = Field(
        default=None,
        description="Warehouse place (None = default/unspecified warehouse)",
    )
    quantity: Decimal = Field(..., ge=0, description="New absolute local quantity")
    reason: str = Field(
        ..., min_length=3, max_length=500, description="Why (audit trail)"
    )


@router.get("", response_model=AdminInventoryList)
async def list_inventory(
    session: SessionDep,
    _admin: CurrentLogisticsAdmin,
    search: str | None = Query(default=None, max_length=200),
    only_local: bool = Query(
        default=False, description="Only products holding local stock"
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminInventoryList:
    """Product-centric stock view (local stock + supplier availability)."""
    statement = (
        select(Product, Inventory)
        .join(Inventory, col(Inventory.product_id) == col(Product.id), isouter=True)
        .where(col(Product.is_active).is_(True))
    )
    count_statement = (
        select(func.count(col(Product.id)))
        .select_from(Product)
        .join(Inventory, col(Inventory.product_id) == col(Product.id), isouter=True)
        .where(col(Product.is_active).is_(True))
    )

    if search:
        needle = f"%{search.strip()}%"
        condition = or_(
            col(Product.name).ilike(needle),
            col(Product.supplier_name).ilike(needle),
        )
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)
    if only_local:
        condition = col(Inventory.quantity) > 0
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    statement = statement.order_by(col(Product.name).asc()).offset(skip).limit(limit)

    rows = await session.exec(statement)
    total = (await session.exec(count_statement)).one()

    items = [
        AdminInventoryItem(
            product_id=product.id,
            product_name=product.name,
            is_supplier_managed=product.is_supplier_managed,
            supplier_name=product.supplier_name,
            supplier_quantity=product.supplier_quantity,
            local_quantity=(
                inventory.quantity if inventory is not None else Decimal("0.00")
            ),
            inventory_id=inventory.id if inventory is not None else None,
            place_id=inventory.place_id if inventory is not None else None,
        )
        for product, inventory in rows.all()
    ]
    return AdminInventoryList(data=items, count=int(total))


@router.post("/adjust", response_model=AdminInventoryItem)
async def adjust_inventory(
    payload: InventoryAdjustRequest,
    session: SessionDep,
    admin: CurrentLogisticsAdmin,
) -> AdminInventoryItem:
    """Set a product's local stock, with a mandatory audited reason.

    Creates the ``Inventory`` row on first use. Writes an ``adjustment``
    movement carrying the delta so the history stays reconstructible.
    """
    product = await session.get(Product, payload.product_id)
    if product is None:
        raise AppError(
            code="inventory.product.not_found",
            status_code=404,
            message=f"Product '{payload.product_id}' not found",
            details={"product_id": str(payload.product_id)},
        )

    inventory = await crud_inventory.get_by_product_and_place(
        session=session,
        product_id=payload.product_id,
        place_id=payload.place_id,
    )
    previous_quantity = inventory.quantity if inventory is not None else Decimal("0.00")
    delta = payload.quantity - previous_quantity

    if inventory is None:
        inventory = await crud_inventory.create_draft(
            session=session,
            data=InventoryCreate(
                product_id=payload.product_id,
                place_id=payload.place_id,
                quantity=payload.quantity,
                compute_from_movements=False,
            ),
            user=admin,
        )
    else:
        inventory.quantity = payload.quantity
        session.add(inventory)

    await crud_stock_movement.create_draft(
        session=session,
        data=InventoryStockMovementCreate(
            movement_type=MovementType.ADJUSTMENT.value,
            reference_type=ReferenceType.MANUAL.value,
            reference_id=None,
            from_place_id=payload.place_id,
            to_place_id=payload.place_id,
            product_id=payload.product_id,
            quantity=abs(delta),
            unit_cost=None,
            reason=(
                f"Ajustement manuel: {previous_quantity} → {payload.quantity} "
                f"(delta {delta:+}) — {payload.reason}"
            ),
            status=MovementStatus.COMPLETED.value,
        ),
        user=admin,
    )

    # Capture everything BEFORE the commit (expired instances otherwise).
    item = AdminInventoryItem(
        product_id=product.id,
        product_name=product.name,
        is_supplier_managed=product.is_supplier_managed,
        supplier_name=product.supplier_name,
        supplier_quantity=product.supplier_quantity,
        local_quantity=payload.quantity,
        inventory_id=inventory.id,
        place_id=payload.place_id,
    )
    await session.commit()
    return item
