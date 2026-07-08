"""Release / confirm the stock reserved at checkout.

The checkout decrements stock at order-draft time (local ``Inventory`` rows
first, then ``product.supplier_quantity``) and writes one PENDING ``outgoing``
movement per fulfillment segment. Until now nothing ever compensated those
reservations: a rejected payment leaked the stock forever (structural
oversell risk — audit finding).

- ``release_order_stock``: puts the reserved quantities back and cancels the
  PENDING movements (payment rejected / order never fulfilled).
- ``confirm_order_stock``: marks the PENDING movements completed (payment
  captured — the consumption becomes final).

Both are idempotent (only PENDING movements are processed) and leave the
commit to the caller.
"""

from __future__ import annotations

import logging
import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.inventory.models.stock_movement import (
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.product.models.product import Product

logger = logging.getLogger(__name__)

# Written by the checkout in the movement reason ("… (segment=local)").
# Movements without this marker are supplier-side reservations.
LOCAL_SEGMENT_MARKER = "segment=local"


async def release_order_stock(session: AsyncSession, *, order_id: uuid.UUID) -> int:
    """Give back the stock reserved for ``order_id`` (idempotent, no commit).

    Local segments credit the ``Inventory`` row they were taken from; supplier
    segments credit ``product.supplier_quantity``. Each processed movement is
    flipped to CANCELLED so a replayed event is a no-op.

    Returns the number of movements released.
    """
    movements = await crud_stock_movement.get_by_reference(
        session,
        reference_type=ReferenceType.ORDER.value,
        reference_id=order_id,
    )
    released = 0
    for movement in movements:
        if (
            movement.movement_type != MovementType.OUTGOING.value
            or movement.status != MovementStatus.PENDING.value
        ):
            continue

        if LOCAL_SEGMENT_MARKER in (movement.reason or ""):
            inventory = await crud_inventory.get_by_product_and_place(
                session=session,
                product_id=movement.product_id,
                place_id=movement.from_place_id,
            )
            if inventory is None:
                logger.warning(
                    "release_order_stock: no inventory row for product %s "
                    "(movement %s) — skipping credit",
                    movement.product_id,
                    movement.id,
                )
            else:
                inventory.quantity += movement.quantity
                session.add(inventory)
        else:
            product = await session.get(Product, movement.product_id)
            if product is None:
                logger.warning(
                    "release_order_stock: product %s gone (movement %s) — "
                    "skipping credit",
                    movement.product_id,
                    movement.id,
                )
            elif product.is_supplier_managed:
                product.supplier_quantity += movement.quantity
                session.add(product)

        movement.status = MovementStatus.CANCELLED.value
        session.add(movement)
        released += 1
    return released


async def confirm_order_stock(session: AsyncSession, *, order_id: uuid.UUID) -> int:
    """Mark the PENDING reservations of ``order_id`` as COMPLETED (no commit)."""
    movements = await crud_stock_movement.get_by_reference(
        session,
        reference_type=ReferenceType.ORDER.value,
        reference_id=order_id,
    )
    confirmed = 0
    for movement in movements:
        if (
            movement.movement_type != MovementType.OUTGOING.value
            or movement.status != MovementStatus.PENDING.value
        ):
            continue
        movement.status = MovementStatus.COMPLETED.value
        session.add(movement)
        confirmed += 1
    return confirmed
