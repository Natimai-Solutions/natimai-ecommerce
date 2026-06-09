"""Outbox handler: supplier_order.shipped → advance tracking to 'shipped'.

When Ingram confirms shipment, we try to advance the corresponding order's
route tracking to the 'shipped' status. If the transition is not allowed
(e.g. already shipped, or the tracking is in a different state), we log a
warning and skip gracefully — the admin can update manually.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_status_definition,
)
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)

_SHIPPED_STATUS_CODE = "shipped"


@outbox_handler("supplier_order.shipped")
async def on_supplier_order_shipped(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Advance route tracking to 'shipped' when Ingram confirms the order."""
    local_order_id_raw = payload.get("local_order_id")
    if not local_order_id_raw:
        logger.warning("supplier_order.shipped: missing local_order_id in payload")
        return

    try:
        order_id = uuid.UUID(str(local_order_id_raw))
    except (TypeError, ValueError):
        logger.warning(
            "supplier_order.shipped: invalid local_order_id %r", local_order_id_raw
        )
        return

    # Find the 'shipped' status definition
    shipped_status = await crud_status_definition.get_by_code(
        session, entity="route_tracking", code=_SHIPPED_STATUS_CODE
    )
    if shipped_status is None:
        logger.warning(
            "supplier_order.shipped: no StatusDefinition with code=%r for entity=route_tracking — cannot advance",
            _SHIPPED_STATUS_CODE,
        )
        return

    # Find all trackings for this order
    trackings = await crud_shipping_route_tracking.get_trackings_by_order_sequence(
        session=session, order_id=order_id
    )
    if not trackings:
        logger.info(
            "supplier_order.shipped: no trackings found for order %s — nothing to advance",
            order_id,
        )
        return

    # Attempt to advance non-terminal trackings to 'shipped'
    advanced = 0
    for tracking in trackings:
        if tracking.status_id == shipped_status.id:
            continue  # already shipped

        try:
            await crud_shipping_route_tracking.update_status(
                session=session,
                tracking_id=tracking.id,
                new_status_id=shipped_status.id,
                changed_by="supplier_webhook",
                reason=f"Auto-advanced by supplier webhook: {payload.get('supplier_status_label')}",
            )
            advanced += 1
        except (ValueError, Exception) as exc:
            logger.warning(
                "supplier_order.shipped: could not advance tracking %s to 'shipped': %s",
                tracking.id,
                exc,
            )

    if advanced:
        logger.info(
            "supplier_order.shipped: advanced %d tracking(s) to 'shipped' for order %s",
            advanced,
            order_id,
        )
