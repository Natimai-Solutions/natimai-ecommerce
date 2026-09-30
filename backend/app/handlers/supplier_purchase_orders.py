"""Outbox handler: place the supplier purchase orders when a payment is captured.

Flow
----
1. Resolve the local order from the payment payload.
2. Skip orders bought with a grouped departure, balances, and parts not yet
   fully paid.
3. Delegate to ``process_purchase_orders``: one purchase order per supplier
   of the order that is set to order automatically (``Supplier.
   auto_purchase_order``, or Ingram with ``INGRAM_ORDER_CREATION_ENABLED``).
4. Re-raise on API failure so the outbox retries with exponential backoff.

Idempotency
-----------
The customer order number sent is the local order UUID; the service also
short-circuits when a ``SUBMITTED`` ``SupplierOrder`` exists for the pair.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.integrations.services.supplier_order_service import (
    process_purchase_orders,
)
from app.features.order.models.order import Order
from app.features.payment.models.payment import Payment
from app.features.payment.services.deposit import KIND_BALANCE
from app.features.payment.services.store_credit import part_coverage
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)


@outbox_handler("payment.captured")
async def on_payment_captured_create_supplier_orders(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Place the purchase orders of the order's suppliers that order automatically."""
    raw_order_id = payload.get("order_id")
    if not raw_order_id:
        logger.debug(
            "payment.captured payload has no order_id — skipping supplier orders"
        )
        return

    try:
        order_id = uuid.UUID(str(raw_order_id))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid order_id %r in payment.captured payload — skipping supplier orders",
            raw_order_id,
        )
        return

    # An order attached to a grouped departure is bought with the departure
    # (aggregated purchase order at close), never one PO per customer order.
    order = await session.get(Order, order_id)
    if order is not None and getattr(order, "grouped_departure_id", None):
        logger.info(
            "Order %s belongs to departure %s — no per-order purchase order",
            order_id,
            order.grouped_departure_id,
        )
        return

    # The deposit is what buys the goods: the balance settles an order whose
    # PO already went out (the service also short-circuits on SUBMITTED). A
    # part still awaiting its money payment (store credit first) waits too.
    raw_payment_id = payload.get("payment_id")
    if raw_payment_id:
        try:
            payment = await session.get(Payment, uuid.UUID(str(raw_payment_id)))
        except (TypeError, ValueError):
            payment = None
        if getattr(payment, "kind", None) == KIND_BALANCE:
            logger.info("Order %s: balance captured — PO already placed", order_id)
            return
        if isinstance(payment, Payment) and order is not None:
            covered, expected, _pending = await part_coverage(
                session, payment=payment, order=order
            )
            if covered < expected:
                logger.info("Order %s: part not fully paid yet — PO deferred", order_id)
                return

    # reraise_on_api_error=True (default): a supplier API failure propagates so
    # the outbox dispatcher retries the message with exponential backoff.
    await process_purchase_orders(session, order_id)
