"""Integration tests: stock released on payment rejection, confirmed on capture.

Real DB — the checkout writes PENDING outgoing movements and decrements
local ``Inventory`` / ``product.supplier_quantity``; ``release_order_stock``
must put both back exactly once (idempotent on event replay).
"""

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

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
)
from app.features.product.models.product import Product


async def _seed(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Product (supplier-managed, hybrid local stock) + order reservations.

    Mirrors what the checkout writes: local stock decremented (2 units) with a
    ``segment=local`` movement, supplier stock decremented (3 units) with a
    supplier-segment movement. Returns (order_id, product_id, inventory_id).
    """
    order_id = uuid.uuid4()
    product = Product(
        name="Produit hybride",
        base_price=Decimal("1000.00"),
        supplier_quantity=Decimal("7.00"),  # 10 - 3 reserved
        is_supplier_managed=True,
    )
    session.add(product)
    await session.flush()

    inventory = Inventory(
        product_id=product.id,
        place_id=None,
        quantity=Decimal("1.00"),  # 3 - 2 reserved
        compute_from_movements=False,
    )
    session.add(inventory)
    await session.flush()

    session.add_all(
        [
            InventoryStockMovement(
                movement_type=MovementType.OUTGOING.value,
                reference_type=ReferenceType.ORDER.value,
                reference_id=order_id,
                product_id=product.id,
                from_place_id=None,
                quantity=Decimal("2.00"),
                reason="Local stock reserved during checkout (segment=local)",
                status=MovementStatus.PENDING.value,
            ),
            InventoryStockMovement(
                movement_type=MovementType.OUTGOING.value,
                reference_type=ReferenceType.ORDER.value,
                reference_id=order_id,
                product_id=product.id,
                from_place_id=None,
                quantity=Decimal("3.00"),
                reason=(
                    "Supplier stock reserved during checkout (segment=supplier_direct)"
                ),
                status=MovementStatus.PENDING.value,
            ),
        ]
    )
    await session.flush()
    return order_id, product.id, inventory.id


@pytest.mark.asyncio
async def test_release_credits_local_and_supplier_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    order_id, product_id, inventory_id = await _seed(db_session)

    released = await release_order_stock(db_session, order_id=order_id)
    await db_session.commit()
    assert released == 2

    product = await db_session.get(Product, product_id)
    inventory = await db_session.get(Inventory, inventory_id)
    assert product is not None and inventory is not None
    # 7 + 3 back = 10 ; 1 + 2 back = 3
    assert product.supplier_quantity == Decimal("10.00")
    assert inventory.quantity == Decimal("3.00")

    # Replayed event (outbox at-least-once): nothing moves twice.
    released_again = await release_order_stock(db_session, order_id=order_id)
    await db_session.commit()
    assert released_again == 0
    product = await db_session.get(Product, product_id)
    inventory = await db_session.get(Inventory, inventory_id)
    assert product is not None and inventory is not None
    assert product.supplier_quantity == Decimal("10.00")
    assert inventory.quantity == Decimal("3.00")


@pytest.mark.asyncio
async def test_confirm_completes_movements_without_touching_stock(
    db_session: AsyncSession,
) -> None:
    order_id, product_id, inventory_id = await _seed(db_session)

    confirmed = await confirm_order_stock(db_session, order_id=order_id)
    await db_session.commit()
    assert confirmed == 2

    product = await db_session.get(Product, product_id)
    inventory = await db_session.get(Inventory, inventory_id)
    assert product is not None and inventory is not None
    # Quantities unchanged — the consumption becomes final.
    assert product.supplier_quantity == Decimal("7.00")
    assert inventory.quantity == Decimal("1.00")

    # A release AFTER confirmation must be a no-op (nothing PENDING left).
    assert await release_order_stock(db_session, order_id=order_id) == 0


@pytest.mark.asyncio
async def test_release_credits_a_manual_product_linked_to_a_supplier(
    db_session: AsyncSession,
) -> None:
    """Audit 2026-11, B5: the checkout takes from ``supplier_quantity`` any
    product with a ``supplier_name``; the release only gave it back to the
    synced ones, so a manual product lost the units for good."""
    order_id = uuid.uuid4()
    product = Product(
        name="Saisi à la main",
        base_price=Decimal("1000.00"),
        supplier_name="grossiste",
        supplier_quantity=Decimal("4.00"),  # 5 - 1 reserved
        is_supplier_managed=False,
    )
    db_session.add(product)
    await db_session.flush()
    product_id = product.id
    db_session.add(
        InventoryStockMovement(
            movement_type=MovementType.OUTGOING.value,
            reference_type=ReferenceType.ORDER.value,
            reference_id=order_id,
            product_id=product_id,
            quantity=Decimal("1.00"),
            reason="Supplier stock reserved during checkout (segment=supplier_direct)",
            status=MovementStatus.PENDING.value,
        )
    )
    await db_session.commit()

    assert await release_order_stock(db_session, order_id=order_id) == 1
    await db_session.commit()
    refreshed = await db_session.get(Product, product_id)
    assert refreshed is not None and refreshed.supplier_quantity == Decimal("5.00")
