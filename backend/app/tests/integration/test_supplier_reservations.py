"""Integration (real DB): the supplier's count still includes the units our
open orders took — a live check or a sync must not give them back to sale
(audit 2026-11, B4)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.integrations.services.checkout_availability import (
    settle_live_supplier_quantities,
)
from app.features.inventory.models.stock_movement import (
    InventoryStockMovement,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.inventory.services.availability import (
    net_supplier_quantity,
    outstanding_supplier_reservations,
)
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.product import Product
from app.features.user.models.user import User


async def _order(session: AsyncSession, user_id: uuid.UUID, status: str) -> uuid.UUID:
    row = OrderStatus(name=status)
    session.add(row)
    await session.flush()
    order = Order(user_id=user_id, order_status_id=row.id, total_amount=Decimal("1"))
    session.add(order)
    await session.flush()
    return order.id


def _taken(
    order_id: uuid.UUID, product_id: uuid.UUID, quantity: str, status: str, local: bool
) -> InventoryStockMovement:
    segment = "local" if local else "supplier_direct"
    return InventoryStockMovement(
        movement_type=MovementType.OUTGOING.value,
        reference_type=ReferenceType.ORDER.value,
        reference_id=order_id,
        product_id=product_id,
        quantity=Decimal(quantity),
        reason=f"reserved during checkout (segment={segment})",
        status=status,
    )


@pytest.mark.asyncio
async def test_open_orders_keep_their_supplier_units(db_session: AsyncSession) -> None:
    user = User(email=f"b+{uuid.uuid4().hex[:6]}@test.local", hashed_password="x")
    product = Product(
        name="Switch",
        base_price=Decimal("100"),
        is_supplier_managed=True,
        supplier_name="ingram",
        supplier_sku=f"SW-{uuid.uuid4().hex[:6]}",
        supplier_quantity=Decimal("0"),
    )
    db_session.add_all([user, product])
    await db_session.flush()
    product_id, sku = product.id, product.supplier_sku
    pending = await _order(db_session, user.id, "Pending")
    paid = await _order(db_session, user.id, "Paid")
    shipped = await _order(db_session, user.id, "OrderedFromSupplier")
    cancelled = await _order(db_session, user.id, "Cancelled")
    db_session.add_all(
        [
            _taken(pending, product_id, "2", MovementStatus.PENDING.value, False),
            _taken(paid, product_id, "3", MovementStatus.COMPLETED.value, False),
            # Already ordered from the supplier: its count no longer has them.
            _taken(shipped, product_id, "5", MovementStatus.COMPLETED.value, False),
            _taken(cancelled, product_id, "7", MovementStatus.CANCELLED.value, False),
            # Our own warehouse: not the supplier's business.
            _taken(paid, product_id, "11", MovementStatus.PENDING.value, True),
        ]
    )
    await db_session.commit()

    held = await outstanding_supplier_reservations(db_session, [product_id])
    assert held == {product_id: Decimal("5")}
    # The supplier says 8: 3 are ours to sell, not 8.
    assert await net_supplier_quantity(db_session, product_id, Decimal("8")) == 3
    assert await net_supplier_quantity(db_session, product_id, Decimal("4")) == 0

    reloaded = await db_session.get(Product, product_id)
    assert reloaded is not None
    await settle_live_supplier_quantities(
        db_session, [reloaded], {str(sku): Decimal("8")}
    )
    assert reloaded.supplier_quantity == Decimal("3")
