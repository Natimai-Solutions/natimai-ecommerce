"""Outbox handler: automatically create an Ingram Micro purchase order when a payment
is captured.

Flow
----
1. Guard on ``INGRAM_ORDER_CREATION_ENABLED`` feature flag.
2. Resolve the local order from the payment payload.
3. Collect order lines whose product is sourced from Ingram Micro.
4. Skip gracefully (no PO needed) when there are no Ingram lines.
5. Validate that the ship-to address is configured (our warehouse, not the customer's).
6. Call ``IngramMicroService.create_purchase_order``.
7. Persist a ``SupplierOrder`` record with the result; re-raise on API failure so the
   outbox retries with exponential backoff.

Idempotency
-----------
``customerOrderNumber`` is the local order UUID, which Ingram uses for deduplication.
On retry the same UUID is sent again and Ingram returns the existing PO rather than
creating a second one. The handler also skips immediately when a SUBMITTED
``SupplierOrder`` already exists for the local order.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.product.models.product import Product
from app.outbox.decorators import outbox_handler
from app.services.suppliers.ingram_micro import IngramMicroService

logger = logging.getLogger(__name__)

_SUPPLIER_NAME = "ingram_micro"


def _build_ship_to() -> dict[str, Any] | None:
    """Build the ship-to address dict from settings.

    Returns None when mandatory fields are missing (address line 1 and city).
    """
    address = settings.INGRAM_SHIP_TO_ADDRESS_LINE1
    city = settings.INGRAM_SHIP_TO_CITY
    if not address or not city:
        return None

    ship_to: dict[str, Any] = {
        "addressLine1": address,
        "city": city,
        "countryCode": settings.INGRAM_SHIP_TO_COUNTRY_CODE or "PF",
    }
    if settings.INGRAM_SHIP_TO_CONTACT:
        ship_to["contact"] = settings.INGRAM_SHIP_TO_CONTACT
    if settings.INGRAM_SHIP_TO_COMPANY_NAME:
        ship_to["companyName"] = settings.INGRAM_SHIP_TO_COMPANY_NAME
    if settings.INGRAM_SHIP_TO_POSTAL_CODE:
        ship_to["postalCode"] = settings.INGRAM_SHIP_TO_POSTAL_CODE
    if settings.INGRAM_SHIP_TO_PHONE:
        ship_to["phoneNumber"] = settings.INGRAM_SHIP_TO_PHONE
    return ship_to


async def _get_existing_supplier_order(
    session: AsyncSession, local_order_id: uuid.UUID
) -> SupplierOrder | None:
    result = await session.exec(
        select(SupplierOrder).where(
            SupplierOrder.local_order_id == local_order_id,
            SupplierOrder.supplier_name == _SUPPLIER_NAME,
        )
    )
    return result.first()


async def _build_ingram_lines(
    session: AsyncSession, order_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Return Ingram order line dicts for all lines in the order that map to an
    Ingram Micro product with a known ``supplier_sku``."""
    order_lines = await crud_order_line.get_by_order(session, order_id=order_id)
    lines: list[dict[str, Any]] = []
    for order_line in order_lines:
        product = await session.get(Product, order_line.product_id)
        if product is None:
            continue
        if product.supplier_name != _SUPPLIER_NAME or not product.supplier_sku:
            continue
        line: dict[str, Any] = {
            "ingramPartNumber": product.supplier_sku,
            "quantity": order_line.quantity,
        }
        # Include cost price in supplier currency when available.
        if product.supplier_price and product.supplier_price > 0:
            line["unitPrice"] = float(product.supplier_price)
        if product.vendor_part_number:
            line["vendorPartNumber"] = product.vendor_part_number
        lines.append(line)
    return lines


async def _save_supplier_order(
    session: AsyncSession,
    *,
    existing: SupplierOrder | None,
    local_order_id: uuid.UUID,
    customer_order_number: str,
    status: SupplierOrderStatus,
    lines_snapshot: list[dict[str, Any]] | None = None,
    supplier_order_number: str | None = None,
    supplier_status_label: str | None = None,
    supplier_response: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> SupplierOrder:
    now = datetime.now(timezone.utc)
    if existing is not None:
        record = existing
    else:
        record = SupplierOrder(
            supplier_name=_SUPPLIER_NAME,
            local_order_id=local_order_id,
            customer_order_number=customer_order_number,
            created_at=now,
        )

    record.status = status
    record.lines_snapshot = lines_snapshot
    record.supplier_order_number = supplier_order_number
    record.supplier_status_label = supplier_status_label
    record.supplier_response = supplier_response
    record.error_message = error_message
    record.attempts = (record.attempts or 0) + 1
    record.updated_at = now

    session.add(record)
    await session.commit()
    return record


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

    # Idempotency guard: a successfully submitted PO is final.
    existing = await _get_existing_supplier_order(session, order_id)
    if existing and existing.status == SupplierOrderStatus.SUBMITTED:
        logger.info(
            "Ingram PO already submitted for order %s (supplier_order=%s), skipping",
            order_id,
            existing.supplier_order_number,
        )
        return

    # Use the order UUID (no hyphens, 32 chars) as the customer order number.
    customer_order_number = str(order_id).replace("-", "")

    # Collect only Ingram-sourced lines.
    ingram_lines = await _build_ingram_lines(session, order_id)
    if not ingram_lines:
        logger.info(
            "Order %s has no Ingram Micro lines — skipping PO creation", order_id
        )
        await _save_supplier_order(
            session,
            existing=existing,
            local_order_id=order_id,
            customer_order_number=customer_order_number,
            status=SupplierOrderStatus.SKIPPED,
            error_message="No Ingram Micro lines in order",
        )
        return

    ship_to = _build_ship_to()
    if ship_to is None:
        logger.error(
            "INGRAM_SHIP_TO_ADDRESS_LINE1 / INGRAM_SHIP_TO_CITY not configured; "
            "cannot create Ingram PO for order %s",
            order_id,
        )
        await _save_supplier_order(
            session,
            existing=existing,
            local_order_id=order_id,
            customer_order_number=customer_order_number,
            status=SupplierOrderStatus.ERROR,
            lines_snapshot=ingram_lines,
            error_message="INGRAM_SHIP_TO_* settings not configured",
        )
        return

    service = IngramMicroService()
    try:
        response = await service.create_purchase_order(
            customer_order_number=customer_order_number,
            lines=ingram_lines,
            ship_to=ship_to,
            notes=f"Local order {order_id}",
        )
    except Exception as exc:
        logger.error(
            "Ingram PO creation failed for order %s: %s", order_id, exc
        )
        await _save_supplier_order(
            session,
            existing=existing,
            local_order_id=order_id,
            customer_order_number=customer_order_number,
            status=SupplierOrderStatus.ERROR,
            lines_snapshot=ingram_lines,
            error_message=str(exc),
        )
        raise  # Let outbox retry with exponential backoff.

    ingram_order_number = response.get("ingramOrderNumber")
    ingram_status = response.get("orderStatus")
    logger.info(
        "Ingram PO created: ingramOrderNumber=%s status=%s for local order %s",
        ingram_order_number,
        ingram_status,
        order_id,
    )

    await _save_supplier_order(
        session,
        existing=existing,
        local_order_id=order_id,
        customer_order_number=customer_order_number,
        status=SupplierOrderStatus.SUBMITTED,
        lines_snapshot=ingram_lines,
        supplier_order_number=ingram_order_number,
        supplier_status_label=ingram_status,
        supplier_response=response,
    )
