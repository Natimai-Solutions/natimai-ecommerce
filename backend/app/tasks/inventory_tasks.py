"""ARQ tasks keeping reserved stock honest.

The checkout decrements stock at order-draft time and writes PENDING outgoing
movements. Those reservations were only ever compensated by ``payment.rejected``
— so a customer who reached the payment page and closed the tab held the stock
forever. On drop-shipped supplier quantities that silently shrinks the sellable
catalog; on local inventory it is a straight oversell risk.

This sweep releases reservations whose order never reached any payment
outcome. Orders sitting in a state a human or an event still drives
(``AwaitingPayment`` for a bank transfer under validation, ``PaymentReview``
after an amount mismatch) are deliberately left alone: rejecting such a
payment from the back office already emits ``payment.rejected``, which
releases the stock through the normal path.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.inventory.crud import crud_stock_movement
from app.features.inventory.services.stock_release import release_order_stock
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus

logger = logging.getLogger(__name__)

#: The order statuses the sweep touches. ``Pending``: created by the checkout,
#: left as soon as any payment outcome lands. ``PaymentFailed``: a new payment
#: attempt takes the stock again (``reserve_released_order_stock``) and may be
#: abandoned too (audit 2026-11, B2).
SWEEPABLE_ORDER_STATUSES: frozenset[str] = frozenset({"Pending", "PaymentFailed"})

#: Orders inspected per run. A sweep is a background chore; capping it keeps
#: one run bounded and lets the next cron pick up the remainder.
SWEEP_BATCH_SIZE = 500


def _now() -> datetime:
    return datetime.now(UTC)


async def release_expired_stock_reservations_task(
    _ctx: dict[str, Any],
    **_kwargs: Any,
) -> dict[str, Any]:
    """Give back stock held by orders that never reached a payment outcome."""
    from app.core import runtime_settings

    ttl_hours = int(await runtime_settings.get("stock_reservation_ttl_hours"))
    if ttl_hours <= 0:
        logger.debug("Stock reservation sweep disabled (TTL <= 0)")
        return {"status": "disabled", "released_orders": 0, "released_movements": 0}

    cutoff = _now() - timedelta(hours=ttl_hours)
    released_orders = 0
    released_movements = 0
    skipped = 0

    async with AsyncSession(engine) as session:
        order_ids = await crud_stock_movement.get_stale_order_reference_ids(
            session,
            older_than=cutoff,
            limit=SWEEP_BATCH_SIZE,
            order_status_names=SWEEPABLE_ORDER_STATUSES,
        )
        if not order_ids:
            return {
                "status": "ok",
                "released_orders": 0,
                "released_movements": 0,
                "skipped_orders": 0,
            }

        for order_id in order_ids:
            order = await session.get(Order, order_id)
            if order is None:
                # Movement pointing at a vanished order: releasing is still the
                # right call, the quantity is not coming back any other way.
                logger.warning(
                    "Stock sweep: order %s no longer exists — releasing anyway",
                    order_id,
                )
            else:
                status = await session.get(OrderStatus, order.order_status_id)
                if getattr(status, "name", None) not in SWEEPABLE_ORDER_STATUSES:
                    # Paid / AwaitingPayment / PaymentReview / refunded: an
                    # event or an operator owns this order, not the sweep.
                    skipped += 1
                    continue

            count = await release_order_stock(session, order_id=order_id)
            if count:
                released_orders += 1
                released_movements += count
                logger.info(
                    "Stock sweep: released %d reservation(s) of order %s "
                    "(no payment outcome after %dh)",
                    count,
                    order_id,
                    ttl_hours,
                )

        if released_movements:
            await session.commit()

    return {
        "status": "ok",
        "released_orders": released_orders,
        "released_movements": released_movements,
        "skipped_orders": skipped,
        "cutoff": cutoff.isoformat(),
    }


def get_stock_reservation_cron_jobs() -> list[Any]:
    """The hourly reservation sweep, always scheduled (R5 / C5): a TTL of 0
    in the runtime settings makes the tick a no-op, without a restart.

    Hourly rather than on the TTL boundary: the TTL decides *what* is stale,
    the cadence only decides how fast a stale reservation is noticed.
    """
    return [
        cron(
            release_expired_stock_reservations_task,  # type: ignore[arg-type]
            minute=45,
            second=0,
            name="release_expired_stock_reservations",
        )
    ]
