"""Core logic for creating Ingram Micro purchase orders from local orders.

Extracted from the outbox handler so it can be reused by the admin manual-retry
endpoint. The function is provider-agnostic in shape but currently targets
Ingram Micro (the only SUPPLIER_DIRECT distributor wired up in Phase 2).

Idempotency
-----------
``customerOrderNumber`` is derived from the local order UUID, which Ingram uses
for deduplication. On retry the same value is sent again and Ingram returns the
existing PO rather than creating a second one. A ``SupplierOrder`` row that is
already ``SUBMITTED`` short-circuits before any API call.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.product.models.product import Product
from app.services.suppliers.ingram_micro import IngramMicroService

logger = logging.getLogger(__name__)

SUPPLIER_NAME = "ingram_micro"


def build_ship_to() -> dict[str, Any] | None:
    """Build the ship-to address dict from settings.

    Returns ``None`` when mandatory fields are missing (address line 1 and city).
    The ship-to is *our* warehouse, never the end customer's address.
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


async def get_existing_supplier_order(
    session: AsyncSession, local_order_id: uuid.UUID
) -> SupplierOrder | None:
    """Return the SupplierOrder tracking this local order for Ingram, if any."""
    result = await session.exec(
        select(SupplierOrder).where(
            SupplierOrder.local_order_id == local_order_id,
            SupplierOrder.supplier_name == SUPPLIER_NAME,
        )
    )
    return result.first()


async def build_ingram_lines(
    session: AsyncSession, order_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Return Ingram order line dicts for every line in the order that maps to an
    Ingram Micro product with a known ``supplier_sku``."""
    order_lines = await crud_order_line.get_by_order(session, order_id=order_id)
    lines: list[dict[str, Any]] = []
    for order_line in order_lines:
        product = await session.get(Product, order_line.product_id)
        if product is None:
            continue
        if product.supplier_name != SUPPLIER_NAME or not product.supplier_sku:
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


async def save_supplier_order(
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
    """Insert or update the SupplierOrder row and increment the attempt counter."""
    now = datetime.now(timezone.utc)
    if existing is not None:
        record = existing
    else:
        record = SupplierOrder(
            supplier_name=SUPPLIER_NAME,
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


async def process_ingram_purchase_order(
    session: AsyncSession,
    order_id: uuid.UUID,
    *,
    reraise_on_api_error: bool = True,
) -> SupplierOrder | None:
    """Create (or no-op) the Ingram Micro PO for a local order.

    Returns the resulting ``SupplierOrder`` (``None`` only when an already
    ``SUBMITTED`` order is short-circuited). The terminal status is encoded on
    the returned record:

    - ``SKIPPED``   — no Ingram-sourced lines in the order.
    - ``ERROR``     — ship-to not configured, or the Ingram API failed.
    - ``SUBMITTED`` — PO accepted by Ingram.

    ``reraise_on_api_error`` controls behaviour on an Ingram API failure:
    the outbox handler passes ``True`` so the message is retried with backoff;
    the admin manual-retry endpoint passes ``False`` so the persisted ``ERROR``
    record is returned to the caller instead of raising.
    """
    existing = await get_existing_supplier_order(session, order_id)
    if existing and existing.status == SupplierOrderStatus.SUBMITTED:
        logger.info(
            "Ingram PO already submitted for order %s (supplier_order=%s), skipping",
            order_id,
            existing.supplier_order_number,
        )
        return existing

    # Use the order UUID (no hyphens, 32 chars) as the customer order number.
    customer_order_number = str(order_id).replace("-", "")

    ingram_lines = await build_ingram_lines(session, order_id)
    if not ingram_lines:
        logger.info(
            "Order %s has no Ingram Micro lines — skipping PO creation", order_id
        )
        return await save_supplier_order(
            session,
            existing=existing,
            local_order_id=order_id,
            customer_order_number=customer_order_number,
            status=SupplierOrderStatus.SKIPPED,
            error_message="No Ingram Micro lines in order",
        )

    ship_to = build_ship_to()
    if ship_to is None:
        logger.error(
            "INGRAM_SHIP_TO_ADDRESS_LINE1 / INGRAM_SHIP_TO_CITY not configured; "
            "cannot create Ingram PO for order %s",
            order_id,
        )
        return await save_supplier_order(
            session,
            existing=existing,
            local_order_id=order_id,
            customer_order_number=customer_order_number,
            status=SupplierOrderStatus.ERROR,
            lines_snapshot=ingram_lines,
            error_message="INGRAM_SHIP_TO_* settings not configured",
        )

    service = IngramMicroService()
    try:
        response = await service.create_purchase_order(
            customer_order_number=customer_order_number,
            lines=ingram_lines,
            ship_to=ship_to,
            notes=f"Local order {order_id}",
        )
    except Exception as exc:
        logger.error("Ingram PO creation failed for order %s: %s", order_id, exc)
        record = await save_supplier_order(
            session,
            existing=existing,
            local_order_id=order_id,
            customer_order_number=customer_order_number,
            status=SupplierOrderStatus.ERROR,
            lines_snapshot=ingram_lines,
            error_message=str(exc),
        )
        if reraise_on_api_error:
            raise  # Let the outbox retry with exponential backoff.
        return record

    ingram_order_number = response.get("ingramOrderNumber")
    ingram_status = response.get("orderStatus")
    logger.info(
        "Ingram PO created: ingramOrderNumber=%s status=%s for local order %s",
        ingram_order_number,
        ingram_status,
        order_id,
    )

    return await save_supplier_order(
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
