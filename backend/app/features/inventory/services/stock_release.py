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
- ``lock_stock_rows``: row-locks the stock of some products, so that a
  reservation or a release computes on the quantities no one else is changing.

Both are idempotent (only PENDING movements are processed) and leave the
commit to the caller.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.inventory.models.inventory import Inventory
from app.features.inventory.models.stock_movement import (
    InventoryStockMovementCreate,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.product.models.product import Product

logger = logging.getLogger(__name__)

# Written by the checkout in the movement reason ("… (segment=local)").
# Movements without this marker are supplier-side reservations.
LOCAL_SEGMENT_MARKER = "segment=local"
# Written on the reservations taken again for a new payment attempt
# (``reserve_released_order_stock``): the checkout's own movements are the
# template, these copies never are.
RERESERVED_MARKER = "re-reserved"


async def lock_stock_rows(
    session: AsyncSession, product_ids: Iterable[uuid.UUID]
) -> None:
    """Lock the products and their inventory rows until the transaction ends.

    The checkout reads the available quantity, then writes it back minus the
    reservation: two concurrent checkouts of the last unit would both read 1
    and both sell it. Under these locks the second one waits, then reads the
    quantity the first one left. The rows are locked in id order (products,
    then inventories) by every caller, so two carts never deadlock; the
    objects already in the session are refreshed with the locked values.
    """
    ids = sorted(set(product_ids))
    if not ids:
        return
    await session.exec(
        select(Product)
        .where(col(Product.id).in_(ids))
        .order_by(col(Product.id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    await session.exec(
        select(Inventory)
        .where(col(Inventory.product_id).in_(ids))
        .order_by(col(Inventory.id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )


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
    pending = [
        movement
        for movement in movements
        if movement.movement_type == MovementType.OUTGOING.value
        and movement.status == MovementStatus.PENDING.value
    ]
    await lock_stock_rows(session, (movement.product_id for movement in pending))
    released = 0
    for movement in pending:
        # Read again under the lock: a concurrent release may have done it.
        await session.refresh(movement)
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
            else:
                # The movement proves the checkout took it from
                # ``supplier_quantity`` (``has_supplier_stock``: synced, or a
                # manual product with a ``supplier_name``): give it back
                # there. Crediting only the synced products lost the stock of
                # the others for good (audit 2026-11, B5).
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


async def reserve_released_order_stock(
    session: AsyncSession, *, order_id: uuid.UUID
) -> int:
    """Take the stock of ``order_id`` again before a new payment attempt
    (audit 2026-11, B2). No commit.

    A refused payment (``payment.rejected``) or the reservation sweep gives
    the stock back, yet the order stays payable: paid later, it was sold
    without stock — ``confirm_order_stock`` found nothing left to confirm.
    When every reservation of the order was released (none PENDING or
    COMPLETED), the checkout's own movements are replayed under the stock
    locks, from the same source (warehouse row or supplier quantity); if one
    no longer has the quantity, nothing is taken and the payment is refused
    (409 ``payment.order.out_of_stock``). Returns the reservations taken.
    """
    movements = [
        movement
        for movement in await crud_stock_movement.get_by_reference(
            session,
            reference_type=ReferenceType.ORDER.value,
            reference_id=order_id,
        )
        if movement.movement_type == MovementType.OUTGOING.value
    ]
    live = {MovementStatus.PENDING.value, MovementStatus.COMPLETED.value}
    if not movements or any(m.status in live for m in movements):
        return 0
    template = [m for m in movements if RERESERVED_MARKER not in (m.reason or "")]
    if not template:
        return 0
    await lock_stock_rows(session, (m.product_id for m in template))

    short: list[str] = []
    plan: list[tuple[Any, Any]] = []
    for movement in template:
        quantity = movement.quantity
        if LOCAL_SEGMENT_MARKER in (movement.reason or ""):
            inventory = await crud_inventory.get_by_product_and_place(
                session=session,
                product_id=movement.product_id,
                place_id=movement.from_place_id,
            )
            held = sum(q for source, q in plan if source is inventory)
            if inventory is None or inventory.quantity - held < quantity:
                short.append(str(movement.product_id))
                continue
            plan.append((inventory, quantity))
        else:
            product = await session.get(Product, movement.product_id)
            held = sum(q for source, q in plan if source is product)
            if product is None or (product.supplier_quantity or 0) - held < quantity:
                short.append(str(movement.product_id))
                continue
            plan.append((product, quantity))
    if short:
        raise AppError(
            code="payment.order.out_of_stock",
            status_code=409,
            message=(
                "Un article de cette commande n'est plus en stock : "
                "elle ne peut plus être payée."
            ),
            details={"order_id": str(order_id), "product_ids": short},
        )

    for (source, quantity), movement in zip(plan, template, strict=True):
        if isinstance(source, Inventory):
            source.quantity -= quantity
        else:
            source.supplier_quantity -= quantity
        session.add(source)
        await crud_stock_movement.create_draft(
            session=session,
            data=InventoryStockMovementCreate(
                movement_type=MovementType.OUTGOING.value,
                reference_type=ReferenceType.ORDER.value,
                reference_id=order_id,
                from_place_id=movement.from_place_id,
                to_place_id=None,
                product_id=movement.product_id,
                quantity=quantity,
                unit_cost=movement.unit_cost,
                reason=f"{movement.reason} ({RERESERVED_MARKER} for a new payment)",
                status=MovementStatus.PENDING.value,
            ),
            user=None,
        )
    return len(plan)
