"""Admin endpoints for supplier purchase orders (Ingram Micro SUPPLIER_DIRECT).

GET  /admin/supplier-orders                 — list with optional status / supplier filters
GET  /admin/supplier-orders/{id}            — single supplier order detail
POST /admin/supplier-orders/{id}/retry      — manually re-attempt PO creation

The automatic creation runs from the ``payment.captured`` outbox handler; these
endpoints give operators visibility and a manual recovery lever when the Ingram
API was unavailable or the ship-to configuration was incomplete at capture time.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query
from sqlmodel import col, func, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderPublic,
    SupplierOrdersPublic,
    SupplierOrderStatus,
)
from app.features.integrations.services.supplier_order_service import (
    process_ingram_purchase_order,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/supplier-orders", tags=["supplier"])


async def _load_supplier_order(
    session: SessionDep, supplier_order_id: uuid.UUID
) -> SupplierOrder:
    record = await session.get(SupplierOrder, supplier_order_id)
    if record is None:
        raise AppError(
            code="supplier_order.not_found",
            status_code=404,
            message=f"Supplier order '{supplier_order_id}' not found",
            details={"supplier_order_id": str(supplier_order_id)},
        )
    return record


@router.get("", response_model=SupplierOrdersPublic)
async def list_supplier_orders(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    status: SupplierOrderStatus | None = Query(
        default=None, description="Filter by supplier order status"
    ),
    supplier_name: str | None = Query(
        default=None, description="Filter by supplier machine name (e.g. ingram_micro)"
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> SupplierOrdersPublic:
    """List supplier orders (most recent first) with optional filters."""
    base_filters = []
    if status is not None:
        base_filters.append(SupplierOrder.status == status)
    if supplier_name is not None:
        base_filters.append(SupplierOrder.supplier_name == supplier_name)

    count_stmt = select(func.count()).select_from(SupplierOrder)
    list_stmt = select(SupplierOrder).order_by(col(SupplierOrder.created_at).desc())
    for condition in base_filters:
        count_stmt = count_stmt.where(condition)
        list_stmt = list_stmt.where(condition)

    count = (await session.exec(count_stmt)).one()
    result = await session.exec(list_stmt.offset(skip).limit(limit))
    records = list(result.all())

    return SupplierOrdersPublic(
        data=[SupplierOrderPublic.model_validate(r) for r in records],
        count=count,
    )


@router.get("/{supplier_order_id}", response_model=SupplierOrderPublic)
async def get_supplier_order(
    supplier_order_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> SupplierOrderPublic:
    """Fetch a single supplier order."""
    record = await _load_supplier_order(session, supplier_order_id)
    return SupplierOrderPublic.model_validate(record)


@router.post("/{supplier_order_id}/retry", response_model=SupplierOrderPublic)
async def retry_supplier_order(
    supplier_order_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> SupplierOrderPublic:
    """Manually re-attempt creating the Ingram PO for this supplier order's local order.

    Idempotent: an already-``SUBMITTED`` order is returned unchanged. On an Ingram
    API failure the persisted ``ERROR`` record is returned (200 with the error
    message) rather than surfacing a 5xx, so operators can read why it failed.
    """
    record = await _load_supplier_order(session, supplier_order_id)

    if record.status == SupplierOrderStatus.SUBMITTED:
        logger.info(
            "Retry no-op: supplier order %s already SUBMITTED (po=%s)",
            supplier_order_id,
            record.supplier_order_number,
        )
        return SupplierOrderPublic.model_validate(record)

    logger.info(
        "Admin %s retrying supplier order %s (local_order=%s, current status=%s)",
        current_user.id,
        supplier_order_id,
        record.local_order_id,
        record.status,
    )
    result = await process_ingram_purchase_order(
        session,
        record.local_order_id,
        reraise_on_api_error=False,
    )
    # result is the same row (updated in place) unless it was already submitted.
    refreshed = result if result is not None else record
    await session.refresh(refreshed)
    return SupplierOrderPublic.model_validate(refreshed)
