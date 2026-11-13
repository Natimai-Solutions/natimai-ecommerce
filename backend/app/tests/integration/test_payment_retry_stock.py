"""Integration (real DB): a new payment attempt takes back the stock a refused
payment (or the reservation sweep) released — audit 2026-11, B2.

The order stays payable after ``payment.rejected``; paid then, it was sold
with no stock behind it."""

from __future__ import annotations

import uuid
from decimal import Decimal
from decimal import Decimal as D

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.inventory.models.inventory import Inventory
from app.features.inventory.models.stock_movement import (
    InventoryStockMovement,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.inventory.services.stock_release import (
    confirm_order_stock,
    release_order_stock,
    reserve_released_order_stock,
)
from app.features.product.models.product import Product


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """An order holding 1 warehouse unit and 2 supplier units (all taken)."""
    order_id = uuid.uuid4()
    product = Product(
        name="Écran",
        base_price=Decimal("1000.00"),
        supplier_name="grossiste",
        supplier_quantity=Decimal("0.00"),  # 2 - 2 reserved
    )
    session.add(product)
    await session.flush()
    product_id = product.id
    inventory = Inventory(
        product_id=product_id,
        quantity=Decimal("0.00"),  # 1 - 1 reserved
        compute_from_movements=False,
    )
    session.add(inventory)
    await session.flush()
    inventory_id = inventory.id
    for quantity, reason in (
        ("1.00", "Local stock reserved during checkout (segment=local)"),
        ("2.00", "Supplier stock reserved during checkout (segment=supplier_direct)"),
    ):
        session.add(
            InventoryStockMovement(
                movement_type=MovementType.OUTGOING.value,
                reference_type=ReferenceType.ORDER.value,
                reference_id=order_id,
                product_id=product_id,
                quantity=Decimal(quantity),
                reason=reason,
                status=MovementStatus.PENDING.value,
            )
        )
    await session.commit()
    return order_id, product_id, inventory_id


async def _stock(
    session: AsyncSession, product_id: uuid.UUID, inventory_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    session.expire_all()
    product = await session.get(Product, product_id)
    inventory = await session.get(Inventory, inventory_id)
    assert product is not None and inventory is not None
    return inventory.quantity, product.supplier_quantity


async def _pending(session: AsyncSession, order_id: uuid.UUID) -> int:
    rows = await session.exec(
        select(InventoryStockMovement).where(
            col(InventoryStockMovement.reference_id) == order_id,
            col(InventoryStockMovement.status) == MovementStatus.PENDING.value,
        )
    )
    return len(rows.all())


@pytest.mark.asyncio
async def test_a_new_attempt_reserves_again_what_a_refusal_released(
    db_session: AsyncSession,
) -> None:
    order_id, product_id, inventory_id = await _seed(db_session)

    # The card is refused: the stock goes back.
    await release_order_stock(db_session, order_id=order_id)
    await db_session.commit()
    assert await _stock(db_session, product_id, inventory_id) == (D(1), D(2))

    # The customer pays again: the same units are taken from the same places.
    assert await reserve_released_order_stock(db_session, order_id=order_id) == 2
    await db_session.commit()
    assert await _stock(db_session, product_id, inventory_id) == (D(0), D(0))
    assert await _pending(db_session, order_id) == 2

    # A second attempt while the reservation holds takes nothing more.
    assert await reserve_released_order_stock(db_session, order_id=order_id) == 0

    # Captured: the new reservations are the ones confirmed.
    assert await confirm_order_stock(db_session, order_id=order_id) == 2
    await db_session.commit()
    assert await reserve_released_order_stock(db_session, order_id=order_id) == 0


@pytest.mark.asyncio
async def test_a_new_attempt_is_refused_once_the_stock_is_gone(
    db_session: AsyncSession,
) -> None:
    order_id, product_id, inventory_id = await _seed(db_session)
    await release_order_stock(db_session, order_id=order_id)
    await db_session.commit()

    # Meanwhile someone else bought the warehouse unit.
    inventory = await db_session.get(Inventory, inventory_id)
    assert inventory is not None
    inventory.quantity = Decimal("0.00")
    await db_session.commit()

    with pytest.raises(AppError) as refused:
        await reserve_released_order_stock(db_session, order_id=order_id)
    assert refused.value.code == "payment.order.out_of_stock"
    await db_session.rollback()
    # Nothing was taken from the supplier stock either.
    assert await _stock(db_session, product_id, inventory_id) == (D(0), D(2))
    assert await _pending(db_session, order_id) == 0


@pytest.mark.asyncio
async def test_released_twice_reserved_twice_never_doubles(
    db_session: AsyncSession,
) -> None:
    """The re-reservation copies the checkout's movements, never its own
    earlier copies: a third attempt takes the same quantities."""
    order_id, product_id, inventory_id = await _seed(db_session)
    for _ in range(2):
        await release_order_stock(db_session, order_id=order_id)
        await db_session.commit()
        assert await reserve_released_order_stock(db_session, order_id=order_id) == 2
        await db_session.commit()
    assert await _stock(db_session, product_id, inventory_id) == (D(0), D(0))
    assert await _pending(db_session, order_id) == 2
