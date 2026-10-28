"""What a customer can do to their own order from « Mes commandes ».

* **Cancel** an order that has received no money yet: the reserved stock and
  the coupon use come back, the pending payments are closed so a late
  provider notification can no longer revive the order, and the order moves
  to ``Cancelled`` (which publishes ``order.status_changed``: e-mail, and the
  release of any card authorisation). Once money is in — a card captured, a
  part settled by store credit, a transfer proof sent — cancelling is a
  refund, which stays with the shop.
* **Order again**: the order's articles go back into the cart at their
  current price; what is no longer sold is left out and reported.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.discount.models import Discount
from app.features.inventory.services.stock_release import release_order_stock
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.status import set_order_status
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_attachment import crud_payment_attachment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatusCreate
from app.features.payment.services.receipts import order_payment_summary
from app.features.payment.services.store_credit import (
    DEAD_PAYMENT_STATUSES,
    SETTLED_PAYMENT_STATUSES,
)

#: Order statuses in which no money has been received yet.
CUSTOMER_CANCELLABLE_STATUSES: frozenset[str] = frozenset(
    {"Pending", "AwaitingPayment", "PaymentFailed"}
)
ORDER_STATUS_CANCELLED = "Cancelled"
#: Status given to the payments of a cancelled order (terminal for the IPN).
PAYMENT_STATUS_CANCELLED = "Cancelled"
CANCEL_REASON = "customer"


async def _status_name(session: AsyncSession, order: Order) -> str | None:
    status = (
        await session.get(OrderStatus, order.order_status_id)
        if order.order_status_id
        else None
    )
    return status.name if status else None


async def cancellation_refusal(session: AsyncSession, order: Order) -> str | None:
    """Why the customer may not cancel ``order`` themselves, or None if they may.

    The reason is a stable code the storefront translates.
    """
    if await _status_name(session, order) not in CUSTOMER_CANCELLABLE_STATUSES:
        return "status"
    summary = await order_payment_summary(session, order=order)
    if summary.paid > Decimal("0"):
        return "paid"
    for payment, status in await crud_payment.list_with_status_by_order_id(
        session, order_id=order.id
    ):
        if status in SETTLED_PAYMENT_STATUSES:
            return "paid"
        if status not in DEAD_PAYMENT_STATUSES and (
            await crud_payment_attachment.list_for_payment(
                session, payment_id=payment.id
            )
        ):
            # A transfer proof is on its way to the shop: the money may be.
            return "proof_sent"
    return None


async def _cancelled_payment_status_id(session: AsyncSession) -> uuid.UUID:
    status = await crud_payment_status.get_by_name(
        session, name=PAYMENT_STATUS_CANCELLED
    )
    if status is None:
        status = await crud_payment_status.create_draft(
            session=session,
            data=PaymentStatusCreate(
                name=PAYMENT_STATUS_CANCELLED,
                description="Order cancelled before any payment",
            ),
            user=None,
        )
        await session.flush()
    return status.id


async def cancel_order_by_customer(
    session: AsyncSession, *, order_id: uuid.UUID, user_id: uuid.UUID
) -> Order:
    """Cancel the customer's own unpaid order; commits.

    The order row is locked first: a payment notification processed at the
    same moment either lands before (the order is then paid, the cancel is
    refused) or after (the payment is closed, the notification is ignored).
    """
    order = (
        await session.exec(
            select(Order)
            .where(col(Order.id) == order_id, col(Order.user_id) == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    if order is None:
        raise AppError(
            code="order.not_found",
            status_code=404,
            message=f"Order {order_id} not found",
            details={"order_id": str(order_id)},
        )
    refusal = await cancellation_refusal(session, order)
    if refusal is not None:
        raise AppError(
            code="order.cancel_refused",
            status_code=409,
            message="This order can no longer be cancelled from the account",
            details={"order_id": str(order_id), "reason": refusal},
        )

    cancelled_id = await _cancelled_payment_status_id(session)
    for payment, status in await crud_payment.list_with_status_by_order_id(
        session, order_id=order.id
    ):
        if status in DEAD_PAYMENT_STATUSES:
            continue
        locked = (
            await session.exec(
                select(Payment)
                .where(col(Payment.id) == payment.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one()
        locked.payment_status_id = cancelled_id
        session.add(locked)

    await release_order_stock(session, order_id=order.id)
    if order.discount_id is not None:
        # The coupon use taken at checkout comes back.
        await session.execute(
            update(Discount)
            .where(
                col(Discount.id) == order.discount_id, col(Discount.current_uses) > 0
            )
            .values(current_uses=Discount.current_uses - 1)
        )
    await set_order_status(
        session,
        order=order,
        status_name=ORDER_STATUS_CANCELLED,
        changed_by_id=user_id,
        reason=CANCEL_REASON,
    )
    await session.commit()
    await session.refresh(order)
    return order


@dataclass
class ReorderResult:
    """Lines put back into the cart, and those that could not be."""

    added: int = 0
    skipped: list[uuid.UUID] = field(default_factory=list)


async def order_lines_to_reorder(
    session: AsyncSession, *, order_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    """``(product_id, quantity)`` of the order's lines, quantities merged."""
    lines = (
        await session.exec(
            select(OrderLine).where(
                col(OrderLine.order_id) == order_id,
                col(OrderLine.is_active).is_(True),
            )
        )
    ).all()
    merged: dict[uuid.UUID, int] = {}
    for line in lines:
        merged[line.product_id] = merged.get(line.product_id, 0) + int(line.quantity)
    return [(product_id, qty) for product_id, qty in merged.items() if qty > 0]
