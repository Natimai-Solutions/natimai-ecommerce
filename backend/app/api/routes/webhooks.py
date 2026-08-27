"""Inbound webhooks from external suppliers.

Phase 3 — Ingram Micro order-status callback:
  POST /webhooks/ingram/order-status

Auth: Bearer token validated against INGRAM_WEBHOOK_SECRET.
If the secret is not configured, the endpoint returns 503 to avoid
silently accepting unauthenticated webhooks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlmodel import or_, select

from app.api.deps import SessionDep
from app.core.config import settings
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.outbox.registry import outbox_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Ingram status labels that indicate the order has been shipped
_SHIPPED_STATUS_LABELS = {
    "shipped",
    "in transit",
    "intransit",
    "dispatched",
    "expedie",
    "expédié",
    "partially shipped",
}


def _extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _is_shipped_label(label: str | None) -> bool:
    """Whether an Ingram status label means the goods have left the warehouse."""
    if not label:
        return False
    normalised = label.strip().lower()
    return any(known in normalised for known in _SHIPPED_STATUS_LABELS)


def _parse_estimated_delivery(raw: Any) -> datetime | None:
    """Try to parse a date/datetime string from the webhook payload."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(raw), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


@router.post("/ingram/order-status")
async def ingram_order_status_webhook(
    request: Request,
    session: SessionDep,
) -> JSONResponse:
    """Receive Ingram order-status callback and update SupplierOrder.

    Publishes ``supplier_order.shipped`` when Ingram confirms the shipment.
    """
    secret = settings.INGRAM_WEBHOOK_SECRET
    if not secret:
        logger.warning(
            "Ingram webhook received but INGRAM_WEBHOOK_SECRET is not set — rejecting"
        )
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Webhook not configured"},
        )

    token = _extract_bearer_token(request)
    if token != secret:
        logger.warning("Ingram webhook: invalid or missing Bearer token")
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Unauthorized"},
        )

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Invalid JSON"},
        )

    logger.info("Ingram order-status webhook received: %s", body)

    # Extract identifiers — Ingram may send either ingramOrderNumber or customerOrderNumber
    ingram_order_number = str(body.get("ingramOrderNumber") or "").strip() or None
    customer_order_number = str(body.get("customerOrderNumber") or "").strip() or None
    new_status_label = (
        str(body.get("orderStatus") or body.get("status") or "").strip().lower()
    )
    estimated_delivery_raw = body.get("estimatedDeliveryDate") or body.get(
        "expectedDeliveryDate"
    )

    if not ingram_order_number and not customer_order_number:
        logger.warning("Ingram webhook: no order identifier in payload")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Missing order identifier"},
        )

    # Look up SupplierOrder
    stmt = select(SupplierOrder).where(
        or_(
            SupplierOrder.supplier_order_number == ingram_order_number
            if ingram_order_number
            else False,
            SupplierOrder.customer_order_number == customer_order_number
            if customer_order_number
            else False,
        )
    )
    result = await session.exec(stmt)
    supplier_order = result.first()

    if supplier_order is None:
        logger.warning(
            "Ingram webhook: no SupplierOrder found for ingram=%s customer=%s",
            ingram_order_number,
            customer_order_number,
        )
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "message": "Order not found — ignored"},
        )

    # Update fields
    was_submitted = supplier_order.status == SupplierOrderStatus.SUBMITTED
    # Ingram retries callbacks, and nothing here moves `status` off SUBMITTED,
    # so `was_submitted` alone would re-publish on every retry. The previous
    # label is the only record of "we already saw the shipment", so compare
    # against it before overwriting. The downstream handler is idempotent, so
    # this is about not queueing pointless work rather than about correctness.
    was_already_shipped = _is_shipped_label(supplier_order.supplier_status_label)
    if new_status_label:
        supplier_order.supplier_status_label = new_status_label

    estimated_delivery = _parse_estimated_delivery(estimated_delivery_raw)
    if estimated_delivery is not None:
        supplier_order.estimated_delivery = estimated_delivery

    session.add(supplier_order)

    # Publish outbox on the *transition* into a shipped state, not on every
    # callback that reports one.
    is_shipped = _is_shipped_label(new_status_label)
    if is_shipped and was_submitted and not was_already_shipped:
        await outbox_registry.publish(
            session=session,
            event_type="supplier_order.shipped",
            payload={
                "supplier_order_id": str(supplier_order.id),
                "local_order_id": str(supplier_order.local_order_id),
                "supplier_name": supplier_order.supplier_name,
                "supplier_order_number": supplier_order.supplier_order_number,
                "supplier_status_label": new_status_label,
                "estimated_delivery": (
                    estimated_delivery.isoformat() if estimated_delivery else None
                ),
            },
            correlation_id=supplier_order.id,
        )

    await session.commit()
    return JSONResponse(content={"status": "ok"})
