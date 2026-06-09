"""Outbox handler: automatically create an Ingram Micro purchase order when a payment
is captured.

Flow
----
1. Guard on ``INGRAM_ORDER_CREATION_ENABLED`` feature flag.
2. Resolve the local order from the payment payload.
3. Delegate to ``process_ingram_purchase_order`` (collect Ingram lines, validate
   ship-to, call the Ingram API, persist a ``SupplierOrder``).
4. Re-raise on API failure so the outbox retries with exponential backoff.

Idempotency
-----------
``customerOrderNumber`` is the local order UUID, which Ingram uses for
deduplication; the service also short-circuits when a ``SUBMITTED``
``SupplierOrder`` already exists for the local order.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.integrations.services.supplier_order_service import (
    process_ingram_purchase_order,
)
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)


@outbox_handler("payment.captured")
async def on_payment_captured_create_ingram_order(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Create an Ingram Micro purchase order for Ingram-sourced lines in the order."""
    if not settings.INGRAM_ORDER_CREATION_ENABLED:
        return

    raw_order_id = payload.get("order_id")
    if not raw_order_id:
        logger.debug(
            "payment.captured payload has no order_id — skipping Ingram PO creation"
        )
        return

    try:
        order_id = uuid.UUID(str(raw_order_id))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid order_id %r in payment.captured payload — skipping Ingram PO",
            raw_order_id,
        )
        return

    # reraise_on_api_error=True (default): an Ingram API failure propagates so the
    # outbox dispatcher retries the message with exponential backoff.
    await process_ingram_purchase_order(session, order_id)
