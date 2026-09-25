"""Order status lifecycle (spec « Communication client »).

One order status conflates payment and fulfilment. The payment statuses are
set by the payment handlers; the fulfilment statuses below are set by the
admin — one order at a time from its detail page, or all the orders of a
grouped departure at once when the departure moves to its next step. Every
change publishes ``order.status_changed`` (customer e-mail, later the balance
request).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus, OrderStatusCreate
from app.outbox.registry import outbox_registry

logger = logging.getLogger(__name__)

EVENT_ORDER_STATUS_CHANGED = "order.status_changed"

#: Set by the payment flow (checkout, IPN, manual validation, refund).
PAYMENT_STATUSES: tuple[str, ...] = (
    "Pending",
    "AwaitingPayment",
    "Paid",
    "PaymentFailed",
    "PaymentReview",
    "Refunded",
    "PartiallyRefunded",
)
#: Set by the admin, in this order along the grouped-departure journey.
FULFILLMENT_STATUSES: tuple[str, ...] = (
    "OrderedFromSupplier",
    "InTransit",
    "AtCustoms",
    "Received",
    "ReadyForPickup",
    "Delivered",
    "Backordered",
    "Cancelled",
)
ALL_ORDER_STATUSES: tuple[str, ...] = PAYMENT_STATUSES + FULFILLMENT_STATUSES

#: Orders that follow their departure's progress: paid, or already on the way.
DEPARTURE_FOLLOWER_STATUSES: frozenset[str] = frozenset(
    {"Paid", "OrderedFromSupplier", "InTransit", "AtCustoms", "Received"}
)
#: Departure status → status pushed to its orders.
DEPARTURE_TO_ORDER_STATUS: dict[str, str] = {
    "ordered": "OrderedFromSupplier",
    "in_transit": "InTransit",
    "at_customs": "AtCustoms",
    "received": "Received",
    "distributed": "ReadyForPickup",
}


async def get_or_create_order_status(session: AsyncSession, name: str) -> OrderStatus:
    """Statuses are rows created by name; a missing one is created on the fly."""
    existing = await crud_order_status.get_by_name(session, name=name)
    if existing is not None:
        return existing
    created = await crud_order_status.create_draft(
        session=session, data=OrderStatusCreate(name=name), user=None
    )
    await session.flush()
    return created


async def set_order_status(
    session: AsyncSession,
    *,
    order: Order,
    status_name: str,
    changed_by_id: uuid.UUID | None,
    reason: str | None = None,
) -> bool:
    """Move ``order`` to ``status_name`` and publish the change.

    Returns False (and does nothing) when the order is already there. Does not
    commit: the caller owns the transaction.
    """
    if status_name not in ALL_ORDER_STATUSES:
        raise ValueError(f"unknown order status '{status_name}'")
    current = await session.get(OrderStatus, order.order_status_id)
    old_name = current.name if current else None
    if old_name == status_name:
        return False

    target = await get_or_create_order_status(session, status_name)
    order.order_status_id = target.id
    session.add(order)

    payload: dict[str, Any] = {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "user_id": str(order.user_id),
        "old_status": old_name,
        "new_status": status_name,
        "grouped_departure_id": (
            str(order.grouped_departure_id) if order.grouped_departure_id else None
        ),
        "reason": reason,
        "changed_by_id": str(changed_by_id) if changed_by_id else None,
    }
    await outbox_registry.publish(
        session=session,
        event_type=EVENT_ORDER_STATUS_CHANGED,
        payload=payload,
        correlation_id=order.id,
    )
    return True


async def propagate_departure_status(
    session: AsyncSession,
    *,
    departure_id: uuid.UUID,
    departure_status: str,
    changed_by_id: uuid.UUID | None,
) -> int:
    """Push the departure's step to every order that follows it.

    Only paid orders (or orders already on the way) move; unpaid, refunded,
    delivered or cancelled ones are left alone. Returns the number of orders
    changed. Does not commit.
    """
    target = DEPARTURE_TO_ORDER_STATUS.get(departure_status)
    if target is None:
        return 0
    follower_ids = select(OrderStatus.id).where(
        col(OrderStatus.name).in_(DEPARTURE_FOLLOWER_STATUSES)
    )
    orders = (
        await session.exec(
            select(Order).where(
                col(Order.grouped_departure_id) == departure_id,
                col(Order.is_active).is_(True),
                col(Order.order_status_id).in_(follower_ids),
            )
        )
    ).all()
    changed = 0
    for order in orders:
        if await set_order_status(
            session,
            order=order,
            status_name=target,
            changed_by_id=changed_by_id,
            reason=f"departure:{departure_status}",
        ):
            changed += 1
    logger.info(
        "Departure %s → %s: %d order(s) moved to %s",
        departure_id,
        departure_status,
        changed,
        target,
    )
    return changed
