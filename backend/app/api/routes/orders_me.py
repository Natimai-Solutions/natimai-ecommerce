"""Customer-facing order endpoints (authenticated user — own orders only).

Phase 3: GET /orders/me/{order_id}/tracking
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter
from fastapi import status as http_status
from sqlmodel import Field, SQLModel, col, select

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.shipping.tracking import (
    _derive_order_exception_scenarios,
    _derive_order_overall_status,
)
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import crud_order
from app.features.order.models.order import OrderPublic
from app.features.order.models.order_status import OrderStatus
from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_status_definition,
)
from app.features.shipping.models.route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingConsolidation,
    ShippingRouteTrackingConsolidationPublic,
    ShippingRouteTrackingPublic,
)
from app.features.shipping.models.status import StatusDefinition

router = APIRouter(prefix="/orders", tags=["order"])


class MyOrderPublic(OrderPublic):
    """Order summary for the customer, enriched with the human-readable status name."""

    order_status_name: str | None = None


class CustomerOrderTrackingResponse(SQLModel):
    """Aggregated tracking view for a customer-owned order."""

    order_id: uuid.UUID
    trackings: list[ShippingRouteTrackingPublic] = Field(default_factory=list)
    current_route_sequence: int | None = None
    overall_status: str
    exception_scenarios: list[str] = Field(default_factory=list)
    consolidations: list[ShippingRouteTrackingConsolidationPublic] = Field(
        default_factory=list
    )


def _carrier_tracking_url(template: str | None, ref: str | None) -> str | None:
    """Build a carrier tracking URL from a ``{ref}`` template, URL-encoding the ref.

    Returns None unless the template is a real https URL and a ref is present
    (https-only guards against a malicious ``javascript:`` template).
    """
    if template and ref and template.startswith("https://"):
        return template.replace("{ref}", quote(ref, safe=""))
    return None


def _to_customer_segment(
    tracking: ShippingRouteTracking,
) -> ShippingRouteTrackingPublic:
    """Public tracking segment enriched with the route leg + carrier tracking link."""
    segment = ShippingRouteTrackingPublic.model_validate(tracking)
    route = tracking.route
    if route is not None:
        segment.from_place_name = route.from_place.name if route.from_place else None
        segment.to_place_name = route.to_place.name if route.to_place else None
        segment.mode = route.mode
        segment.route_label = route.customer_label or route.name
    carrier = tracking.carrier
    if carrier is not None:
        segment.carrier_name = carrier.name
        segment.tracking_url = _carrier_tracking_url(
            carrier.tracking_url_template, tracking.tracking_ref
        )
    return segment


@router.get(
    "/me",
    response_model=list[MyOrderPublic],
    summary="List my orders",
)
async def list_my_orders(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> list[MyOrderPublic]:
    """List the authenticated user's orders (most recent first)."""
    orders = await crud_order.get_by_user(
        session=session, user_id=current_user.id, skip=skip, limit=limit
    )

    # Resolve the order-status names in one query so the customer sees a readable
    # status (Payée / En attente de paiement…) rather than an opaque UUID.
    status_ids = {o.order_status_id for o in orders if o.order_status_id}
    name_by_id: dict[uuid.UUID, str] = {}
    if status_ids:
        result = await session.exec(
            select(OrderStatus).where(col(OrderStatus.id).in_(status_ids))
        )
        name_by_id = {status.id: status.name for status in result.all()}

    items: list[MyOrderPublic] = []
    for order in orders:
        item = MyOrderPublic.model_validate(order)
        item.order_status_name = name_by_id.get(order.order_status_id)
        items.append(item)
    return items


@router.get(
    "/me/{order_id}/tracking",
    response_model=CustomerOrderTrackingResponse,
    summary="Get tracking for my order",
)
async def get_my_order_tracking(
    order_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> CustomerOrderTrackingResponse:
    """Return aggregated tracking information for one of the authenticated user's orders."""
    try:
        order = await crud_order.read(session, id=order_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="order.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Order {order_id} not found",
            details={"order_id": str(order_id)},
        ) from exc

    if order.user_id != current_user.id:
        raise AppError(
            code="order.not_owned",
            status_code=http_status.HTTP_403_FORBIDDEN,
            message="You cannot access this order",
            details={"order_id": str(order_id)},
        )

    trackings = await crud_shipping_route_tracking.get_trackings_by_order_sequence(
        session=session, order_id=order_id
    )

    if not trackings:
        return CustomerOrderTrackingResponse(
            order_id=order_id,
            overall_status="unknown",
        )

    # Only the consolidations THIS order's trackings actually belong to
    # (deduplicated) — not every consolidation that shares the route.
    consolidations_by_id: dict[uuid.UUID, ShippingRouteTrackingConsolidation] = {}
    for t in trackings:
        if t.consolidation is not None:
            consolidations_by_id[t.consolidation.id] = t.consolidation

    status_defs = await crud_status_definition.get_by_entity(
        session=session, entity="route_tracking"
    )
    status_by_id: dict[uuid.UUID, StatusDefinition] = {s.id: s for s in status_defs}

    current_sequence, overall_status = _derive_order_overall_status(
        trackings, status_by_id=status_by_id
    )
    exception_scenarios = _derive_order_exception_scenarios(
        trackings, status_by_id=status_by_id
    )

    return CustomerOrderTrackingResponse(
        order_id=order_id,
        trackings=[_to_customer_segment(t) for t in trackings],
        current_route_sequence=current_sequence,
        overall_status=overall_status,
        exception_scenarios=exception_scenarios,
        consolidations=[
            ShippingRouteTrackingConsolidationPublic.model_validate(c)
            for c in consolidations_by_id.values()
        ],
    )
