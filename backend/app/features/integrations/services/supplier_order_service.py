"""Supplier purchase orders placed on behalf of local orders (R4 / S4).

When a customer order is paid, its lines are grouped by supplier; every
supplier whose integration can order (``SupplierAdapter.
supports_purchase_orders``) and that is set to order automatically
(``Supplier.auto_purchase_order``) gets one purchase order, delivered to the
shop's **main warehouse** (``Place.is_main_warehouse``). One
``SupplierOrder`` row tracks each (local order, supplier) pair.

``INGRAM_ORDER_CREATION_ENABLED`` / ``INGRAM_SHIP_TO_*`` are the historical,
Ingram-only settings: the flag still turns Ingram's automatic orders on, and
the ship-to fields fill what the main warehouse does not carry (contact,
phone) or replace it when no main warehouse has an address.

Idempotency
-----------
``customer_order_number`` is derived from the local order UUID (the supplier
deduplicates on it when it can). A ``SupplierOrder`` row already
``SUBMITTED`` short-circuits before any API call.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.integrations.models.supplier import Supplier
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.product.models.product import Product
from app.features.shipping.services.origin import get_main_warehouse
from app.services.suppliers import (
    ADAPTERS,
    adapter_for_supplier,
    is_api_supplier,
    load_supplier,
)
from app.services.suppliers.base import PurchaseOrderLine, ShipTo, SupplierAdapter

logger = logging.getLogger(__name__)

#: The historical distributor (its env flag still switches its orders on).
INGRAM_CODE = "ingram_micro"


def customer_order_number(order_id: uuid.UUID) -> str:
    """The order UUID without hyphens (32 chars): the dedup key sent along."""
    return str(order_id).replace("-", "")


def _legacy_ship_to() -> ShipTo | None:
    address = settings.INGRAM_SHIP_TO_ADDRESS_LINE1
    city = settings.INGRAM_SHIP_TO_CITY
    if not address or not city:
        return None
    return ShipTo(
        address_line1=address,
        city=city,
        country_code=settings.INGRAM_SHIP_TO_COUNTRY_CODE or "PF",
        company_name=settings.INGRAM_SHIP_TO_COMPANY_NAME,
        contact=settings.INGRAM_SHIP_TO_CONTACT,
        postal_code=settings.INGRAM_SHIP_TO_POSTAL_CODE,
        phone=settings.INGRAM_SHIP_TO_PHONE,
    )


async def build_ship_to(session: AsyncSession) -> ShipTo | None:
    """Our delivery address: the main warehouse, else the ``INGRAM_SHIP_TO_*``.

    ``None`` when neither carries an address line and a city.
    """
    warehouse = await get_main_warehouse(session)
    if warehouse is not None and warehouse.address_line1 and warehouse.city:
        return ShipTo(
            address_line1=warehouse.address_line1,
            address_line2=warehouse.address_line2,
            city=warehouse.city,
            postal_code=warehouse.postal_code,
            country_code=(
                warehouse.country
                or settings.INGRAM_SHIP_TO_COUNTRY_CODE
                or settings.SHOP_COUNTRY_CODE
            ),
            company_name=settings.INGRAM_SHIP_TO_COMPANY_NAME or settings.SHOP_NAME,
            contact=settings.INGRAM_SHIP_TO_CONTACT,
            phone=settings.INGRAM_SHIP_TO_PHONE,
        )
    return _legacy_ship_to()


def orders_automatically(supplier: Supplier) -> bool:
    """The supplier is set to receive a purchase order at payment."""
    if not supplier.is_active or not is_api_supplier(supplier):
        return False
    if not ADAPTERS[str(supplier.adapter_key)].supports_purchase_orders:
        return False
    if supplier.auto_purchase_order:
        return True
    return supplier.code == INGRAM_CODE and bool(settings.INGRAM_ORDER_CREATION_ENABLED)


async def get_existing_supplier_order(
    session: AsyncSession, local_order_id: uuid.UUID, supplier_name: str = INGRAM_CODE
) -> SupplierOrder | None:
    """The SupplierOrder tracking this local order at this supplier, if any."""
    result = await session.exec(
        select(SupplierOrder).where(
            SupplierOrder.local_order_id == local_order_id,
            SupplierOrder.supplier_name == supplier_name,
        )
    )
    return result.first()


async def lines_by_supplier(
    session: AsyncSession, order_id: uuid.UUID
) -> dict[str, list[PurchaseOrderLine]]:
    """The order's lines that come from a supplier reference, per supplier."""
    grouped: dict[str, list[PurchaseOrderLine]] = defaultdict(list)
    for order_line in await crud_order_line.get_by_order(session, order_id=order_id):
        product = await session.get(Product, order_line.product_id)
        if product is None or not product.supplier_name or not product.supplier_sku:
            continue
        price = product.supplier_price
        grouped[product.supplier_name].append(
            PurchaseOrderLine(
                supplier_sku=product.supplier_sku,
                quantity=int(order_line.quantity),
                unit_price=Decimal(str(price)) if price and price > 0 else None,
                vendor_part_number=product.vendor_part_number,
            )
        )
    return dict(grouped)


def _snapshot(lines: list[PurchaseOrderLine]) -> list[dict[str, Any]]:
    return [
        {
            "supplier_sku": line.supplier_sku,
            "quantity": line.quantity,
            **(
                {"unit_price": float(line.unit_price)}
                if line.unit_price is not None
                else {}
            ),
            **(
                {"vendor_part_number": line.vendor_part_number}
                if line.vendor_part_number
                else {}
            ),
        }
        for line in lines
    ]


async def save_supplier_order(
    session: AsyncSession,
    *,
    existing: SupplierOrder | None,
    supplier_name: str,
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
    record = existing or SupplierOrder(
        supplier_name=supplier_name,
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
    # Committing expired it; callers read the outcome right away.
    await session.refresh(record)
    return record


async def process_supplier_purchase_order(
    session: AsyncSession,
    order_id: uuid.UUID,
    supplier_name: str,
    *,
    lines: list[PurchaseOrderLine] | None = None,
    adapter: SupplierAdapter | None = None,
    reraise_on_api_error: bool = True,
) -> SupplierOrder:
    """Place (or no-op) the purchase order of ``order_id`` at ``supplier_name``.

    Terminal status on the returned record: ``SKIPPED`` (no line of this
    supplier), ``ERROR`` (no integration able to order, no delivery address,
    or the supplier refused / was unreachable), ``SUBMITTED``.

    ``reraise_on_api_error``: the outbox handler lets an API failure propagate
    so the message is retried with backoff; the admin retry gets the persisted
    ``ERROR`` record back instead.
    """
    existing = await get_existing_supplier_order(session, order_id, supplier_name)
    if existing and existing.status == SupplierOrderStatus.SUBMITTED:
        logger.info(
            "PO already submitted at %s for order %s (%s), skipping",
            supplier_name,
            order_id,
            existing.supplier_order_number,
        )
        return existing

    number = customer_order_number(order_id)
    if lines is None:
        lines = (await lines_by_supplier(session, order_id)).get(supplier_name, [])
    common: dict[str, Any] = {
        "existing": existing,
        "supplier_name": supplier_name,
        "local_order_id": order_id,
        "customer_order_number": number,
    }
    if not lines:
        return await save_supplier_order(
            session,
            **common,
            status=SupplierOrderStatus.SKIPPED,
            error_message=f"No {supplier_name} lines in order",
        )
    snapshot = _snapshot(lines)

    if adapter is None:
        supplier = await load_supplier(session, supplier_name, include_inactive=True)
        if supplier is not None and is_api_supplier(supplier):
            adapter = adapter_for_supplier(supplier)
    if adapter is None or not adapter.supports_purchase_orders:
        return await save_supplier_order(
            session,
            **common,
            status=SupplierOrderStatus.ERROR,
            lines_snapshot=snapshot,
            error_message=(
                f"{supplier_name} has no integration able to place purchase orders"
            ),
        )

    ship_to = await build_ship_to(session)
    if ship_to is None:
        logger.error(
            "No delivery address (main warehouse or INGRAM_SHIP_TO_*): cannot "
            "order %s from %s",
            order_id,
            supplier_name,
        )
        return await save_supplier_order(
            session,
            **common,
            status=SupplierOrderStatus.ERROR,
            lines_snapshot=snapshot,
            error_message=(
                "Adresse de livraison absente : renseignez l'adresse de "
                "l'entrepôt principal (ou INGRAM_SHIP_TO_*)"
            ),
        )

    try:
        result = await adapter.create_purchase_order(
            customer_order_number=number,
            lines=lines,
            ship_to=ship_to,
            notes=f"Local order {order_id}",
        )
    except Exception as exc:
        logger.error("PO at %s failed for order %s: %s", supplier_name, order_id, exc)
        record = await save_supplier_order(
            session,
            **common,
            status=SupplierOrderStatus.ERROR,
            lines_snapshot=snapshot,
            error_message=str(exc),
        )
        if reraise_on_api_error:
            raise  # Let the outbox retry with exponential backoff.
        return record

    logger.info(
        "PO placed at %s: %s (%s) for local order %s",
        supplier_name,
        result.order_number,
        result.status_label,
        order_id,
    )
    return await save_supplier_order(
        session,
        **common,
        status=SupplierOrderStatus.SUBMITTED,
        lines_snapshot=snapshot,
        supplier_order_number=result.order_number,
        supplier_status_label=result.status_label,
        supplier_response=result.raw,
    )


async def process_purchase_orders(
    session: AsyncSession,
    order_id: uuid.UUID,
    *,
    reraise_on_api_error: bool = True,
) -> list[SupplierOrder]:
    """One purchase order per supplier of the order set to order automatically.

    Suppliers are processed one after the other; an API failure at one is
    re-raised only after the others were attempted (their ``SUBMITTED`` rows
    make the outbox retry skip them).
    """
    grouped = await lines_by_supplier(session, order_id)
    records: list[SupplierOrder] = []
    failure: Exception | None = None
    for supplier_name, lines in grouped.items():
        supplier = await load_supplier(session, supplier_name, include_inactive=True)
        if supplier is None or not orders_automatically(supplier):
            continue
        adapter = adapter_for_supplier(supplier)
        try:
            records.append(
                await process_supplier_purchase_order(
                    session,
                    order_id,
                    supplier_name,
                    lines=lines,
                    adapter=adapter,
                    reraise_on_api_error=reraise_on_api_error,
                )
            )
        except Exception as exc:  # noqa: BLE001 - re-raised below
            failure = failure or exc
    if failure is not None:
        raise failure
    return records


async def process_ingram_purchase_order(
    session: AsyncSession,
    order_id: uuid.UUID,
    *,
    reraise_on_api_error: bool = True,
) -> SupplierOrder | None:
    """Ingram only (kept for callers of the Ingram-era API)."""
    return await process_supplier_purchase_order(
        session, order_id, INGRAM_CODE, reraise_on_api_error=reraise_on_api_error
    )


__all__ = [
    "INGRAM_CODE",
    "build_ship_to",
    "customer_order_number",
    "get_existing_supplier_order",
    "lines_by_supplier",
    "orders_automatically",
    "process_ingram_purchase_order",
    "process_purchase_orders",
    "process_supplier_purchase_order",
    "save_supplier_order",
]
