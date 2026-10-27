"""Customer-facing order endpoints (authenticated user — own orders only).

Phase 3: GET /orders/me/{order_id}/tracking
"""

from __future__ import annotations

import uuid
from decimal import Decimal

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
from app.features.departure.reception import MyOrderLine, customer_lines
from app.features.order.crud.order_crud import crud_order
from app.features.order.models.order import Order, OrderPublic
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.customer_actions import (
    cancel_order_by_customer,
    cancellation_refusal,
)
from app.features.order.services.tracking_link import (
    tracking_link_still_valid,
    verify_order_tracking_token,
)
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.services.deposit import balance_amount, balance_due
from app.features.payment.services.receipts import order_payment_summary
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
from app.features.shipping.services.tracking_url import carrier_tracking_url

router = APIRouter(prefix="/orders", tags=["order"])


class MyOrderPublic(OrderPublic):
    """Order summary for the customer, enriched with the human-readable status name."""

    order_status_name: str | None = None
    # Deposit order: what is left to pay (0 otherwise) and whether it is
    # being asked for right now (goods received, balance not settled).
    balance_amount: Decimal = Decimal("0.00")
    balance_due: bool = False


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


# Kept under its historical name: the URL builder now lives in the shipping
# services so the admin journey can reuse it.
_carrier_tracking_url = carrier_tracking_url


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
        item.balance_amount = balance_amount(order)
        item.balance_due = balance_due(order)
        items.append(item)
    return items


async def _my_order_or_error(
    session: SessionDep, order_id: uuid.UUID, current_user: CurrentUser
) -> Order:
    try:
        order: Order = await crud_order.read(session, id=order_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="order.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Order {order_id} not found",
            details={"order_id": str(order_id)},
        ) from exc
    if order.user_id != current_user.id:
        # Someone else's order reads like an unknown one: no existence oracle.
        raise AppError(
            code="order.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Order {order_id} not found",
            details={"order_id": str(order_id)},
        )
    return order


class MyOrderDetail(MyOrderPublic):
    """One order for its detail page: the summary plus how it was paid."""

    payment_method_name: str | None = None
    #: Money already received (instalments included) and what is left to pay.
    amount_paid: Decimal = Decimal("0")
    amount_due: Decimal = Decimal("0")
    #: Whether « Annuler la commande » is offered (nothing paid yet).
    can_cancel: bool = False


async def _payment_method_name(session: SessionDep, order_id: uuid.UUID) -> str | None:
    """Name of the payment method of the order's most recent payment."""
    result = await session.exec(
        select(PaymentMethod.name)
        .join(Payment, col(Payment.payment_method_id) == col(PaymentMethod.id))
        .where(col(Payment.order_id) == order_id)
        .order_by(col(Payment.created_at).desc().nulls_last())
        .limit(1)
    )
    return result.first()


@router.get(
    "/me/{order_id}",
    response_model=MyOrderDetail,
    summary="One of my orders",
)
async def get_my_order(
    order_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> MyOrderDetail:
    """A single order of the authenticated user, with its status name and the
    payment method used. Replaces reloading the whole list to find one."""
    order = await _my_order_or_error(session, order_id, current_user)
    item = MyOrderDetail.model_validate(order)
    if order.order_status_id:
        status = await session.get(OrderStatus, order.order_status_id)
        item.order_status_name = status.name if status else None
    item.balance_amount = balance_amount(order)
    item.balance_due = balance_due(order)
    item.payment_method_name = await _payment_method_name(session, order.id)
    summary = await order_payment_summary(session, order=order)
    item.amount_paid, item.amount_due = summary.paid, summary.due
    item.can_cancel = await cancellation_refusal(session, order) is None
    return item


@router.post(
    "/me/{order_id}/cancel",
    response_model=MyOrderDetail,
    summary="Cancel one of my orders before it is paid",
)
async def cancel_my_order(
    order_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> MyOrderDetail:
    """The customer cancels an order that has received no money yet: stock
    and coupon come back, pending payments are closed. A paid order is a
    refund, asked from the shop (409 ``order.cancel_refused``)."""
    await cancel_order_by_customer(session, order_id=order_id, user_id=current_user.id)
    # The commit expired the session's objects, the signed-in user included.
    await session.refresh(current_user)
    return await get_my_order(order_id, session, current_user)


@router.get(
    "/me/{order_id}/lines",
    response_model=list[MyOrderLine],
    summary="Lines of my order, with serial numbers and warranty end",
)
async def get_my_order_lines(
    order_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> list[MyOrderLine]:
    """Products of the order; serial numbers and warranty end once received."""
    order = await _my_order_or_error(session, order_id, current_user)
    return await customer_lines(session, order)


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
    await _my_order_or_error(session, order_id, current_user)
    return await _tracking_for(session, order_id)


class TrackedOrderResponse(SQLModel):
    """Everything the tracking page shows, for the holder of a signed link."""

    order: MyOrderPublic
    tracking: CustomerOrderTrackingResponse
    lines: list[MyOrderLine] = Field(default_factory=list)


@router.get(
    "/track/{order_id}",
    response_model=TrackedOrderResponse,
    summary="Follow an order from the signed link in its e-mails (no account)",
)
async def track_order_by_link(
    order_id: uuid.UUID, session: SessionDep, t: str | None = None
) -> TrackedOrderResponse:
    """The link in the order e-mails carries a signature of the order id:
    it opens that one order's tracking, read-only, without signing in.
    A wrong or missing signature reads like an unknown order."""
    if not verify_order_tracking_token(order_id, t if isinstance(t, str) else None):
        raise AppError(
            code="order.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Order {order_id} not found",
            details={"order_id": str(order_id)},
        )
    try:
        order: Order = await crud_order.read(session, id=order_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="order.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Order {order_id} not found",
            details={"order_id": str(order_id)},
        ) from exc
    if not tracking_link_still_valid(order.created_at):
        # A forwarded e-mail stops showing the order (and its address) once
        # the order is long done: the customer's account still does.
        raise AppError(
            code="order.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Order {order_id} not found",
            details={"order_id": str(order_id)},
        )
    view = MyOrderPublic.model_validate(order)
    status = (
        await session.get(OrderStatus, order.order_status_id)
        if order.order_status_id
        else None
    )
    view.order_status_name = status.name if status else None
    view.balance_amount = balance_amount(order)
    view.balance_due = balance_due(order)
    return TrackedOrderResponse(
        order=view,
        tracking=await _tracking_for(session, order_id),
        lines=await customer_lines(session, order),
    )


async def _tracking_for(
    session: SessionDep, order_id: uuid.UUID
) -> CustomerOrderTrackingResponse:
    """Aggregated tracking of an order whose access has been checked."""
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
