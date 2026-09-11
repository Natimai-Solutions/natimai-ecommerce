import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Query, status
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.core.observability import log_structured_event, observe_checkout_result
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.crud.quote_request import crud_quote_request
from app.features.cart.models.cart import (
    Cart,
    CartDetailPublic,
    CartItem,
    CartItemAddRequest,
    CartItemDetail,
    CartItemQuantityUpdateRequest,
    CartReplaceRequest,
    CheckoutQuoteResponse,
    CheckoutRequest,
    CheckoutResponse,
    CheckoutShippingPreference,
    LastLegOption,
    LastLegOptionsResponse,
)
from app.features.cart.models.quote_request import (
    GuestQuoteRequestResponse,
    GuestQuoteRequestSubmit,
    QuoteRequest,
    QuoteRequestCreate,
    QuoteRequestResponse,
    QuoteRequestStatus,
    QuoteRequestSubmit,
)
from app.features.discount.services.checkout_discount import (
    AppliedDiscount,
    DiscountRefused,
    consume_coupon,
    resolve_coupon,
)
from app.features.integrations.services.checkout_availability import (
    refresh_supplier_availability,
)
from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.inventory.models.stock_movement import (
    InventoryStockMovementCreate,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.inventory.services.availability import supplier_available_quantity
from app.features.notification.email_renderer import render_email
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order import OrderCreate
from app.features.order.models.order_line import OrderLineCreate
from app.features.order.models.order_status import OrderStatus, OrderStatusCreate
from app.features.order.services.order_number import allocate_order_number
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import PaymentCreate
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
)
from app.features.payment.services.payment_initiation import (
    PaymentInitiationResult,
    initiate_payment_for_method,
)
from app.features.place.crud import crud_place
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.features.product.services.pricing import (
    calculate_sale_price,
    product_applies_customs,
    resolve_default_price_group,
    resolve_effective_customs_rate_pct,
    resolve_tax_rate,
)
from app.features.product.services.publication import publication_blockers
from app.features.shipping.crud import (
    crud_shipping_route,
    crud_shipping_route_tracking,
    crud_shipping_route_tracking_consolidation,
    crud_status_definition,
)
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_tracking import (
    ShippingRouteTrackingConsolidationCreate,
    ShippingRouteTrackingCreate,
)
from app.features.shipping.models.status import StatusDefinition, StatusDefinitionCreate
from app.features.shipping.services import (
    CustomsDeclarationFee,
    ShippingCostSummary,
    calculate_shipping_for_routes,
    serialize_shipping_cost_summary,
)
from app.features.shipping.services.last_leg import resolve_last_leg_candidates
from app.features.shipping.services.origin import (
    get_main_warehouse,
    load_origin_context,
)
from app.features.user.crud.address import crud_address
from app.features.user.models.address import Address, AddressCreate
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry
from app.utils.money import quantize_amount

EVENT_ORDER_CREATED = "order.created"

_PENDING_ORDER_STATUS = "Pending"
_PENDING_PAYMENT_STATUS = "Pending"

logger = logging.getLogger(__name__)


class FulfillmentSegment(str, Enum):
    """Where an allocation is served from, and how it reaches the customer.

    Values are frozen: they are written into ``OrderLine.notes``
    (``fulfillment_segments=…``) and read back by reports and tests.
    """

    LOCAL = "local"  # own stock in the main warehouse
    SUPPLIER_DIRECT = "supplier_direct"  # dropshipping: supplier → customer
    # Supplier goods regrouped at the main warehouse before the last leg.
    # Historical value: the flow was born on the Polynesia corridor.
    VIA_MAIN_WAREHOUSE = "consolidation_pf"
    CONSOLIDATION_PF = "consolidation_pf"  # alias, kept for older call sites


@dataclass(frozen=True)
class FulfillmentAllocation:
    """Represents fulfillment allocation."""

    segment: FulfillmentSegment
    quantity: Decimal
    # Origin place of this allocation (own warehouse for LOCAL, supplier origin
    # for supplier segments). Drives the first-leg route; None → generic fallback.
    origin_place_id: uuid.UUID | None = None


_FULFILLMENT_SEGMENT_PRIORITY: dict[FulfillmentSegment, int] = {
    FulfillmentSegment.LOCAL: 1,
    FulfillmentSegment.SUPPLIER_DIRECT: 2,
    FulfillmentSegment.VIA_MAIN_WAREHOUSE: 2,
}


def _supplier_segment_for_origin(origin: Place | None) -> FulfillmentSegment:
    """How goods bought from this supplier reach the customer.

    Read from the supplier's place, never from the address text: a place
    flagged ``dropship_enabled`` ships straight to the customer; every other
    supplier's goods regroup at the main warehouse first.
    """
    if origin is not None and origin.dropship_enabled is True:
        return FulfillmentSegment.SUPPLIER_DIRECT
    return FulfillmentSegment.VIA_MAIN_WAREHOUSE


def _plan_checkout_fulfillment_segments(
    *,
    product: Product,
    quantity: int,
    local_available: Decimal,
    supplier_available: Decimal,
    supplier_segment: FulfillmentSegment = FulfillmentSegment.VIA_MAIN_WAREHOUSE,
    local_place_id: uuid.UUID | None = None,
    supplier_place_id: uuid.UUID | None = None,
) -> list[FulfillmentAllocation]:
    """Split a line between local stock and the supplier (``supplier_segment``)."""
    requested_quantity = Decimal(quantity)
    total_available = local_available + supplier_available

    if total_available < requested_quantity:
        raise AppError(
            code="cart.stock.insufficient",
            status_code=409,
            message=(
                f"Insufficient stock for product {product.id}: "
                f"requested={requested_quantity}, "
                f"local_available={local_available}, "
                f"supplier_available={supplier_available}"
            ),
            details={
                "product_id": str(product.id),
                "requested": str(requested_quantity),
                "local_available": str(local_available),
                "supplier_available": str(supplier_available),
            },
        )

    local_to_reserve = min(local_available, requested_quantity)
    supplier_to_reserve = requested_quantity - local_to_reserve

    segments: list[FulfillmentAllocation] = []
    if local_to_reserve > 0:
        segments.append(
            FulfillmentAllocation(
                segment=FulfillmentSegment.LOCAL,
                quantity=local_to_reserve,
                origin_place_id=local_place_id,
            )
        )

    if supplier_to_reserve > 0:
        segments.append(
            FulfillmentAllocation(
                segment=supplier_segment,
                quantity=supplier_to_reserve,
                origin_place_id=supplier_place_id,
            )
        )

    return segments


def _format_fulfillment_segments_note(
    segments: list[FulfillmentAllocation],
) -> str | None:
    """Execute format fulfillment segments note."""
    if not segments:
        return None

    def _format_quantity(quantity: Decimal) -> str:
        """Execute format quantity."""
        if quantity == quantity.to_integral_value():
            return str(int(quantity))
        return format(quantity.normalize(), "f")

    serialized_segments = ",".join(
        f"{segment.segment.value}:{_format_quantity(segment.quantity)}"
        for segment in segments
    )
    return f"fulfillment_segments={serialized_segments}"


def _route_total_cost(
    route: ShippingRoute,
    *,
    total_weight_kg: Decimal,
    declared_value: Decimal,
    currency: str,
) -> Decimal:
    """Execute route total cost."""
    summary = calculate_shipping_for_routes(
        routes=[route],
        total_weight_kg=total_weight_kg,
        declared_value=declared_value,
        currency=currency,
    )
    return summary.total_fee


def _route_preference_sort_key(
    route: ShippingRoute,
    preference: CheckoutShippingPreference,
    *,
    total_weight_kg: Decimal,
    declared_value: Decimal,
    currency: str,
) -> tuple[float, float, float]:
    """Execute route preference sort key."""
    route_priority = float(route.priority if route.priority is not None else 999)
    eta_days = float(route.eta_days if route.eta_days is not None else 9999)
    carbon = (
        route.carbon_footprint_kg_co2e
        if route.carbon_footprint_kg_co2e is not None
        else 999999.0
    )

    if preference == CheckoutShippingPreference.FASTEST:
        return (eta_days, carbon, route_priority)

    if preference == CheckoutShippingPreference.ECO_FRIENDLY:
        return (carbon, eta_days, route_priority)

    # CHEAPEST: rank by the actually recomputed segment cost (not display priority).
    route_cost = float(
        _route_total_cost(
            route,
            total_weight_kg=total_weight_kg,
            declared_value=declared_value,
            currency=currency,
        )
    )
    return (route_cost, eta_days, route_priority)


async def _import_route_ids(
    session: SessionDep,
    routes: list[ShippingRoute],
) -> set[uuid.UUID]:
    """Ids of the routes among ``routes`` that cross the customs border.

    A route is an import leg when its destination clears customs
    (``Place.customs_clearance``). Its variable freight already sits inside the
    product's CAF unit price (see product/services/pricing.py), so billing it
    again as a cart shipping fee would charge the import twice.
    """
    if not routes:
        return set()

    to_place_ids = {route.to_place_id for route in routes}
    result = await session.exec(
        select(col(Place.id)).where(
            col(Place.id).in_(to_place_ids),
            col(Place.customs_clearance).is_(True),
        )
    )
    customs_place_ids = set(result.all())
    return {route.id for route in routes if route.to_place_id in customs_place_ids}


async def _customs_declaration_fees(
    session: SessionDep,
    products: Sequence[Product] = (),
) -> list[CustomsDeclarationFee]:
    """Fixed charges owed once per customs declaration for this shipment.

    The fee lives on the customs ``Place`` and not on the route: several
    corridors (France, US, Asie…) landing at the same border still produce a
    single declaration, and deduplicating by place is what keeps it that way.
    Only borders actually served by an active route are billed, and an unset
    (or zero) fee bills nothing — the amount is a deployment parameter, like
    the customs rates of F1/F2.

    Nothing is billed when every product comes from a domestic origin (a
    supplier in the main warehouse's country — see shipping/services/
    origin.py): such an order clears no customs. A product without a
    configured origin keeps the historical behaviour and is billed.

    Two known limitations, both erring on the over-charging side (which is
    visible and refundable, unlike under-charging): an order served entirely
    from local stock clears no customs yet pays the fee — the line-to-segment
    allocation only happens later, inside the checkout transaction — and when
    several orders are consolidated into one declaration, each carries the
    whole fee. Set the amount to the expected per-order share until the
    logistics phase makes the billing consolidation-aware.
    """
    if products:
        origin_context = await load_origin_context(session)
        crossing = [
            await product_applies_customs(session, product, context=origin_context)
            for product in products
        ]
        if not any(crossing):
            return []

    active_route_destinations = select(col(ShippingRoute.to_place_id)).where(
        col(ShippingRoute.is_active).is_(True)
    )
    result = await session.exec(
        select(Place).where(
            col(Place.customs_clearance).is_(True),
            col(Place.customs_declaration_fee) > 0,
            col(Place.id).in_(active_route_destinations),
        )
    )
    return [
        CustomsDeclarationFee(
            place_id=place.id,
            place_name=place.name,
            amount=Decimal(str(place.customs_declaration_fee)),
        )
        for place in result.all()
    ]


async def _resolve_selected_checkout_routes(
    session: SessionDep,
    *,
    shipping_route_ids: list[uuid.UUID],
) -> list[ShippingRoute]:
    """Execute resolve selected checkout routes."""
    if not shipping_route_ids:
        return []

    ordered_route_ids: list[uuid.UUID] = []
    seen_route_ids: set[uuid.UUID] = set()

    for route_id in shipping_route_ids:
        if route_id in seen_route_ids:
            continue
        seen_route_ids.add(route_id)
        ordered_route_ids.append(route_id)

    statement = select(ShippingRoute).where(
        col(ShippingRoute.id).in_(ordered_route_ids),
        col(ShippingRoute.is_active).is_(True),
    )
    result = await session.exec(statement)
    routes = list(result.all())

    route_by_id = {route.id: route for route in routes}
    missing_route_ids = [
        str(route_id) for route_id in ordered_route_ids if route_id not in route_by_id
    ]
    if missing_route_ids:
        raise AppError(
            code="shipping.route.unknown_or_inactive",
            status_code=400,
            message="Unknown or inactive shipping routes: "
            + ", ".join(missing_route_ids),
            details={"route_ids": missing_route_ids},
        )

    import_route_ids = await _import_route_ids(session, routes)
    if import_route_ids:
        raise AppError(
            code="shipping.route.import_not_billable",
            status_code=400,
            message=(
                "Import routes are already priced into the product and cannot "
                "be charged as shipping: "
                + ", ".join(sorted(str(rid) for rid in import_route_ids))
            ),
            details={"route_ids": sorted(str(rid) for rid in import_route_ids)},
        )

    return [route_by_id[route_id] for route_id in ordered_route_ids]


async def _select_checkout_routes_by_preference(
    session: SessionDep,
    *,
    preference: CheckoutShippingPreference | None,
    total_weight_kg: Decimal,
    declared_value: Decimal,
    currency: str,
    include_customer_routes: bool = True,
) -> list[ShippingRoute]:
    """Automatic route selection for API clients that send a preference.

    ``include_customer_routes=False`` when the checkout carries a
    ``delivery_type``: the last leg is then the route the customer explicitly
    chose, and picking "the fastest customer route" here on top of it would
    bill two last legs (and track the wrong one) whenever they differ.
    """
    if preference is None:
        return []

    def sort_key(route: ShippingRoute) -> tuple[float, float, float]:
        """Execute sort key."""
        return _route_preference_sort_key(
            route,
            preference,
            total_weight_kg=total_weight_kg,
            declared_value=declared_value,
            currency=currency,
        )

    selected_routes: list[ShippingRoute] = []

    intermediary_routes = await crud_shipping_route.get_intermediary_routes(
        session=session,
    )
    # Drop the import legs: their freight is already in the product price.
    import_ids = await _import_route_ids(session, intermediary_routes)
    intermediary_routes = [r for r in intermediary_routes if r.id not in import_ids]
    if intermediary_routes:
        selected_routes.append(min(intermediary_routes, key=sort_key))

    if not include_customer_routes:
        return selected_routes

    customer_routes = await crud_shipping_route.get_customer_routes(session=session)
    if customer_routes:
        selected_customer_route = min(customer_routes, key=sort_key)
        if not selected_routes or selected_routes[-1].id != selected_customer_route.id:
            selected_routes.append(selected_customer_route)

    return selected_routes


def _compute_checkout_declared_value_and_weight(
    *,
    items: list[CartItem],
    products_by_id: dict[uuid.UUID, Product],
) -> tuple[Decimal, Decimal]:
    """Compute checkout declared value and weight."""
    declared_value = Decimal("0")
    total_weight_kg = Decimal("0")

    for item in items:
        product = products_by_id[item.product_id]
        item_quantity = Decimal(item.quantity)
        declared_value += item.unit_price * item_quantity

        product_weight_value = getattr(product, "weight", None)
        if product_weight_value is not None:
            product_weight = Decimal(str(product_weight_value))
            if product_weight > 0:
                total_weight_kg += product_weight * item_quantity

    return declared_value, total_weight_kg


async def _resolve_tracking_address_for_checkout(
    session: SessionDep,
    *,
    current_user: User,
    shipping_address: str | None,
    shipping_address_id: uuid.UUID | None = None,
) -> Address:
    """Execute resolve tracking address for checkout.

    When ``shipping_address_id`` points to one of the customer's own addresses,
    that record is linked directly — no text rematching, no duplicate creation.
    Otherwise falls back to matching ``shipping_address`` text, then to creating
    a snapshot address (guest/manual entry).
    """
    existing_shipping_addresses = await crud_address.get_by_user_and_type(
        session=session,
        user_id=current_user.id,
        address_type="shipping",
    )

    if shipping_address_id is not None:
        for address in existing_shipping_addresses:
            if address.id == shipping_address_id:
                return address

    if shipping_address:
        normalized_shipping_address = shipping_address.strip().lower()
        for address in existing_shipping_addresses:
            candidate = (
                ", ".join(
                    [
                        address.street,
                        address.city,
                        address.country,
                    ]
                )
                .strip()
                .lower()
            )
            if candidate == normalized_shipping_address:
                return address

    if existing_shipping_addresses and not shipping_address:
        return existing_shipping_addresses[0]

    if shipping_address:
        chunks = [
            chunk.strip() for chunk in shipping_address.split(",") if chunk.strip()
        ]
    else:
        chunks = []

    street = chunks[0] if chunks else "Checkout shipping address"
    city = chunks[1] if len(chunks) > 1 else "Unknown"
    country = chunks[-1] if chunks else settings.SHOP_COUNTRY_CODE

    return await crud_address.create_draft(
        session=session,
        data=AddressCreate(
            user_id=current_user.id,
            street=street,
            city=city,
            state=None,
            postal_code="00000",
            country=country,
            type="shipping",
        ),
        user=current_user,
    )


async def _get_or_create_tracking_status(
    session: SessionDep,
    *,
    entity: str,
    code: str,
    name: str,
) -> StatusDefinition:
    """Get or create tracking status."""
    status_record = await crud_status_definition.get_by_code(
        session=session,
        entity=entity,
        code=code,
    )
    if status_record is not None:
        return status_record

    return await crud_status_definition.create_draft(
        session=session,
        data=StatusDefinitionCreate(
            entity=entity,
            code=code,
            name=name,
            description=f"Auto-created status for {entity}",
            sequence_order=0,
            is_terminal=False,
            is_error=False,
            ui_color=None,
            ui_icon=None,
        ),
        user=None,
    )


async def _get_main_warehouse_place_id(session: SessionDep) -> uuid.UUID | None:
    """The main warehouse flagged in the database (``Place.is_main_warehouse``),
    with the historical fallbacks — see shipping/services/origin.py."""
    warehouse = await get_main_warehouse(session)
    return warehouse.id if warehouse is not None else None


async def _destination_chain_for_address(
    session: SessionDep,
    *,
    address: Address | None,
) -> list[uuid.UUID]:
    """Destination chain of an address, nearest zone first (île → ... → pays).

    Empty when the address has no resolved zone — only destination-independent
    delivery modes (always_available / legacy unscoped) are then offered.
    """
    if address is None or address.place_id is None:
        return []
    chain = await crud_place.get_ancestor_chain(session, place_id=address.place_id)
    return [place.id for place in chain]


async def _load_user_address(
    session: SessionDep,
    *,
    user_id: uuid.UUID,
    address_id: uuid.UUID | None,
) -> Address | None:
    """One of the user's own addresses, or None (foreign ids are rejected)."""
    if address_id is None:
        return None
    result = await session.exec(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == user_id,
            col(Address.is_active).is_(True),
        )
    )
    return result.first()


async def _resolve_last_leg_route(
    session: SessionDep,
    *,
    delivery_type: str | None,
    destination_chain: list[uuid.UUID] | None = None,
) -> ShippingRoute | None:
    """Active last-leg route (``is_to_customer``) priced for the chosen delivery mode.

    The admin tags each last-leg route with a free-form ``last_leg_delivery_type``
    (e.g. ``home_delivery``, ``air_freight``, ``sea_freight``…); the checkout maps
    the customer's ``delivery_type`` to that route so its tariff (base_price +
    price_per_kg × weight) is added to the order total. Modes are not a fixed
    enum — any value an admin configures on a route becomes a selectable mode.

    When a ``destination_chain`` is given, only routes serving that destination
    qualify (most specific zone first) — see ``resolve_last_leg_candidates``.
    """
    if not delivery_type:
        return None
    candidates = await resolve_last_leg_candidates(
        session, destination_chain=destination_chain or []
    )
    candidate = candidates.get(delivery_type)
    return candidate.route if candidate is not None else None


async def _resolve_tracking_path_for_segment(
    session: SessionDep,
    *,
    segment: FulfillmentSegment,
    origin_place_id: uuid.UUID | None = None,
) -> list[ShippingRoute]:
    """Upstream legs (in order) bringing a segment's goods to the main warehouse.

    When the allocation's origin place is known (e.g. a supplier's warehouse),
    the legs are the optimal path from that origin to the main warehouse — every
    hop, so a supplier → hub → warehouse journey is tracked hop by hop. Falls
    back to the generic single-route heuristic when no origin / no path is
    found. Empty when nothing can be resolved.
    """
    if origin_place_id is not None:
        main_warehouse_id = await _get_main_warehouse_place_id(session)
        if main_warehouse_id is not None and main_warehouse_id != origin_place_id:
            path = await crud_shipping_route.get_optimal_route_between_places(
                session=session,
                from_place_id=origin_place_id,
                to_place_id=main_warehouse_id,
                is_to_customer=False,
            )
            if path:
                return list(path)

    fallback = await _resolve_tracking_route_for_segment(
        session=session, segment=segment, origin_place_id=None
    )
    return [fallback] if fallback is not None else []


async def _resolve_tracking_route_for_segment(
    session: SessionDep,
    *,
    segment: FulfillmentSegment,
    origin_place_id: uuid.UUID | None = None,
) -> ShippingRoute | None:
    """Execute resolve tracking route for segment.

    When the allocation's origin place is known (e.g. a supplier's warehouse),
    the first leg is the optimal route from that origin to the main warehouse.
    Falls back to the generic heuristic when no origin / no path is found.
    """
    if origin_place_id is not None:
        main_warehouse_id = await _get_main_warehouse_place_id(session)
        if main_warehouse_id is not None and main_warehouse_id != origin_place_id:
            path = await crud_shipping_route.get_optimal_route_between_places(
                session=session,
                from_place_id=origin_place_id,
                to_place_id=main_warehouse_id,
                is_to_customer=False,
            )
            if path:
                return path[0]  # first leg of the resolved journey

    if segment == FulfillmentSegment.VIA_MAIN_WAREHOUSE:
        intermediary_routes = await crud_shipping_route.get_intermediary_routes(
            session=session,
            allow_consolidation=True,
        )
        if intermediary_routes:
            return intermediary_routes[0]

    customer_routes = await crud_shipping_route.get_customer_routes(session=session)

    if segment == FulfillmentSegment.LOCAL:
        if customer_routes:
            return customer_routes[0]
    elif segment == FulfillmentSegment.SUPPLIER_DIRECT:
        for route in customer_routes:
            if not route.allow_consolidation:
                return route
        if customer_routes:
            return customer_routes[0]
    elif segment == FulfillmentSegment.VIA_MAIN_WAREHOUSE:
        for route in customer_routes:
            if route.allow_consolidation:
                return route
        if customer_routes:
            return customer_routes[0]

    fallback_statement = (
        select(ShippingRoute)
        .where(col(ShippingRoute.is_active).is_(True))
        .order_by(col(ShippingRoute.priority).asc())
        .limit(1)
    )
    fallback_result = await session.exec(fallback_statement)
    return fallback_result.first()


async def _link_fulfillment_segments_to_tracking(
    session: SessionDep,
    *,
    order_id: uuid.UUID,
    current_user: User,
    shipping_address: str | None,
    shipping_address_id: uuid.UUID | None = None,
    segment_totals: dict[tuple[FulfillmentSegment, uuid.UUID | None], Decimal],
    last_leg_route: ShippingRoute | None = None,
) -> None:
    """Create the order's journey (one tracking per leg) from its fulfillment.

    With ``last_leg_route`` (the route behind the customer's ``delivery_type``)
    the journey is: upstream legs bringing supplier goods to the main
    warehouse — none for goods already in local stock — then ONE final leg on
    that route. A one-warehouse shop therefore gets exactly one tracking, on
    the carrier the customer chose; a supplier-sourced order gets
    supplier → warehouse → customer.

    Without it (legacy API callers), each segment keeps its heuristic route.
    """
    if not segment_totals:
        return

    shipping_address_record = await _resolve_tracking_address_for_checkout(
        session=session,
        current_user=current_user,
        shipping_address=shipping_address,
        shipping_address_id=shipping_address_id,
    )

    route_tracking_status = await _get_or_create_tracking_status(
        session=session,
        entity="route_tracking",
        code="pending",
        name="Pending",
    )
    consolidation_status = await _get_or_create_tracking_status(
        session=session,
        entity="consolidation",
        code="pending",
        name="Pending",
    )

    ordered_segments = sorted(
        segment_totals.items(),
        key=lambda item: (
            _FULFILLMENT_SEGMENT_PRIORITY[item[0][0]],
            item[0][0].value,
            str(item[0][1] or ""),
        ),
    )

    async def _create_leg(
        route: ShippingRoute,
        *,
        sequence_order: int,
        consolidation_id: uuid.UUID | None = None,
    ) -> None:
        await crud_shipping_route_tracking.create_draft(
            session=session,
            data=ShippingRouteTrackingCreate(
                order_id=order_id,
                route_id=route.id,
                status_id=route_tracking_status.id,
                address_id=shipping_address_record.id,
                consolidation_id=consolidation_id,
                selected_at=datetime.now(timezone.utc),
                sequence_order=sequence_order,
                last_status_update=None,
                tracking_ref=None,
                estimated_delivery=None,
                # `notes` is customer-facing (ShippingRouteTrackingPublic); keep
                # internal linkage out of it (sequence/route already convey it).
                notes=None,
            ),
            user=current_user,
        )

    sequence_order = 0
    needs_shared_last_leg = False
    for (segment, origin_place_id), quantity in ordered_segments:
        if last_leg_route is not None and segment == FulfillmentSegment.LOCAL:
            # Goods already sit in the warehouse: the final leg below is their
            # whole journey.
            needs_shared_last_leg = True
            continue

        if last_leg_route is not None and segment == FulfillmentSegment.SUPPLIER_DIRECT:
            # Dropshipping: one leg from the supplier straight to the customer,
            # on the supplier's own customer route when one is configured,
            # else on the delivery mode the customer chose.
            sequence_order += 1
            direct_route = await _resolve_dropship_route(
                session, origin_place_id=origin_place_id
            )
            await _create_leg(
                direct_route or last_leg_route, sequence_order=sequence_order
            )
            continue

        if last_leg_route is not None:
            needs_shared_last_leg = True
            legs = await _resolve_tracking_path_for_segment(
                session=session,
                segment=segment,
                origin_place_id=origin_place_id,
            )
            # The heuristic may fall back to a customer route; the chosen
            # last leg already covers that hop.
            legs = [leg for leg in legs if not leg.is_to_customer]
        else:
            selected_route = await _resolve_tracking_route_for_segment(
                session=session,
                segment=segment,
                origin_place_id=origin_place_id,
            )
            legs = [selected_route] if selected_route is not None else []

        if not legs:
            if last_leg_route is None:
                logger.warning(
                    "D2 skipped: no shipping route available for segment=%s "
                    "order_id=%s",
                    segment.value,
                    order_id,
                )
            continue

        for leg_index, leg in enumerate(legs):
            sequence_order += 1
            consolidation_id = None
            if leg_index == 0 and segment == FulfillmentSegment.VIA_MAIN_WAREHOUSE:
                consolidation = (
                    await crud_shipping_route_tracking_consolidation.create_draft(
                        session=session,
                        data=ShippingRouteTrackingConsolidationCreate(
                            route_id=leg.id,
                            name=f"Regroupement entrepôt {order_id}",
                            consolidation_code=(
                                f"pf-{str(order_id)[:8]}-{sequence_order}"
                            ),
                            status_id=consolidation_status.id,
                            tracking_ref=None,
                            total_orders=1,
                            notes=(
                                f"Auto-created from checkout segment={segment.value} "
                                f"quantity={quantity}"
                            ),
                        ),
                        user=current_user,
                    )
                )
                consolidation_id = consolidation.id

            await _create_leg(
                leg,
                sequence_order=sequence_order,
                consolidation_id=consolidation_id,
            )

    if last_leg_route is not None and needs_shared_last_leg:
        await _create_leg(last_leg_route, sequence_order=sequence_order + 1)


async def _resolve_dropship_route(
    session: SessionDep, *, origin_place_id: uuid.UUID | None
) -> ShippingRoute | None:
    """Customer-delivery route leaving the supplier's place (dropshipping)."""
    if origin_place_id is None:
        return None
    routes = await crud_shipping_route.get_customer_routes(
        session=session, from_place_id=origin_place_id
    )
    return routes[0] if routes else None


async def _link_selected_routes_to_tracking(
    session: SessionDep,
    *,
    order_id: uuid.UUID,
    current_user: User,
    shipping_address: str | None,
    shipping_address_id: uuid.UUID | None = None,
    selected_routes: list[ShippingRoute],
) -> None:
    """Execute link selected routes to tracking."""
    if not selected_routes:
        return

    shipping_address_record = await _resolve_tracking_address_for_checkout(
        session=session,
        current_user=current_user,
        shipping_address=shipping_address,
        shipping_address_id=shipping_address_id,
    )

    route_tracking_status = await _get_or_create_tracking_status(
        session=session,
        entity="route_tracking",
        code="pending",
        name="Pending",
    )

    for sequence_order, route in enumerate(selected_routes, start=1):
        await crud_shipping_route_tracking.create_draft(
            session=session,
            data=ShippingRouteTrackingCreate(
                order_id=order_id,
                route_id=route.id,
                status_id=route_tracking_status.id,
                address_id=shipping_address_record.id,
                consolidation_id=None,
                selected_at=datetime.now(timezone.utc),
                sequence_order=sequence_order,
                last_status_update=None,
                tracking_ref=None,
                estimated_delivery=None,
                # Customer-facing field — no internal linkage metadata here.
                notes=None,
            ),
            user=current_user,
        )


def _snapshot_checkout_amounts(
    *,
    items: list[CartItem],
    currency: str,
    shipping_fee_amount: Decimal,
    payment_fee_amount: Decimal,
    discount_amount: Decimal = Decimal("0.00"),
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Subtotal (gross lines), fees, and the total net of the promo discount."""
    subtotal_amount = sum(
        (item.unit_price * item.quantity for item in items),
        Decimal("0.00"),
    )
    subtotal_amount = quantize_amount(subtotal_amount, currency)

    shipping_fee = quantize_amount(shipping_fee_amount, currency)
    payment_fee = quantize_amount(payment_fee_amount, currency)
    total_fees_amount = quantize_amount(shipping_fee + payment_fee, currency)
    discount = min(quantize_amount(discount_amount, currency), subtotal_amount)
    total_amount = quantize_amount(
        subtotal_amount - discount + total_fees_amount, currency
    )

    return (
        subtotal_amount,
        shipping_fee,
        payment_fee,
        total_fees_amount,
        total_amount,
    )


async def _revalidate_checkout_prices(
    session: SessionDep,
    *,
    items: list[CartItem],
    products_by_id: dict[uuid.UUID, Product],
    currency: str,
) -> None:
    """Refuse to bill a stale price, and refresh the cart so the client sees why.

    ``CartItem.unit_price`` is snapshotted when the line is added, but the
    catalog moves under it: a supplier sync every two hours rewrites the cost,
    and FX or customs changes re-derive the sale price. The checkout used to
    sum those snapshots and bill them, discarding the freshly computed price it
    had just resolved for every product.

    Billing more than the displayed price is not something the customer agreed
    to; billing less quietly loses margin. So any drift, in either direction,
    stops the checkout — the cart is updated first, so the customer sees the
    new price and re-confirms.
    """
    drifted: list[dict[str, str]] = []
    for item in items:
        product = products_by_id[item.product_id]
        # base_price was recomputed by _get_active_product_or_404.
        current = quantize_amount(product.base_price, currency)
        snapshot = quantize_amount(item.unit_price, currency)
        if current == snapshot:
            continue

        drifted.append(
            {
                "product_id": str(item.product_id),
                "product_name": product.name,
                "previous_unit_price": str(snapshot),
                "current_unit_price": str(current),
            }
        )
        item.unit_price = current
        session.add(item)

    if not drifted:
        return

    # Persist the refreshed prices before bailing out: the client re-reads the
    # cart on this error, and must be shown the price it is being asked to
    # accept, not the stale one it just tried to pay.
    await session.commit()

    raise AppError(
        code="cart.price.changed",
        status_code=409,
        message=(
            "Le prix de certains articles a changé depuis leur ajout au panier. "
            "Vérifiez le nouveau montant avant de valider."
        ),
        details={"currency": currency, "items": drifted},
    )


async def _resolve_payment_fee(
    session: SessionDep,
    *,
    payment_method_id: uuid.UUID | None,
    currency: str,
) -> Decimal:
    """Read the payment fee from the chosen method, never from the client.

    The storefront used to send ``payment_fee_amount`` and the backend took it
    at face value, so the amount charged for the payment method was decided by
    the caller. The fee is a property of the method — it is read here.
    """
    if payment_method_id is None:
        return Decimal("0.00")

    method = await session.get(PaymentMethod, payment_method_id)
    if method is None:
        # Not our error to raise: initiate_payment_for_method reports the
        # unknown/ineligible method with its own contract.
        return Decimal("0.00")
    return quantize_amount(method.fee, currency)


async def _get_or_create_order_pending_status(session: SessionDep) -> OrderStatus:
    """Get or create order pending status."""
    status_record = await crud_order_status.get_by_name(
        session,
        name=_PENDING_ORDER_STATUS,
    )
    if status_record is not None:
        return status_record

    return await crud_order_status.create_draft(
        session=session,
        data=OrderStatusCreate(name=_PENDING_ORDER_STATUS),
        user=None,
    )


async def _get_or_create_payment_pending_status(
    session: SessionDep,
) -> PaymentStatus:
    """Get or create payment pending status."""
    status_record = await crud_payment_status.get_by_name(
        session,
        name=_PENDING_PAYMENT_STATUS,
    )
    if status_record is not None:
        return status_record

    return await crud_payment_status.create_draft(
        session=session,
        data=PaymentStatusCreate(
            name=_PENDING_PAYMENT_STATUS,
            description="Payment created at checkout and awaiting processing",
        ),
        user=None,
    )


async def _reserve_stock_for_checkout(
    session: SessionDep,
    *,
    order_id: uuid.UUID,
    product: Product,
    quantity: int,
    current_user: User,
) -> list[FulfillmentAllocation]:
    """Reserve local stock first, then the supplier's; return the allocations."""
    quantity_decimal = Decimal(quantity)
    inventory = await crud_inventory.get_by_product_and_place(
        session=session,
        product_id=product.id,
        place_id=None,
    )

    local_available = inventory.quantity if inventory is not None else Decimal("0.00")
    # Supplier stock counts for every product that has a supplier: the synced
    # ones (refreshed by the inventory sync) and the manual ones linked to a
    # generic supplier, whose quantity the admin maintains by hand or by file.
    # Same rule as the storefront display (inventory/services/availability).
    supplier_available = supplier_available_quantity(product)

    supplier_place_id = getattr(product, "supplier_place_id", None)
    supplier_place = (
        await session.get(Place, supplier_place_id)
        if supplier_place_id is not None
        else None
    )

    segments = _plan_checkout_fulfillment_segments(
        product=product,
        quantity=quantity,
        local_available=local_available,
        supplier_available=supplier_available,
        supplier_segment=_supplier_segment_for_origin(supplier_place),
        local_place_id=inventory.place_id if inventory is not None else None,
        supplier_place_id=supplier_place_id,
    )

    for segment in segments:
        if segment.segment == FulfillmentSegment.LOCAL:
            if inventory is None:
                raise AppError(
                    code="cart.stock.insufficient",
                    status_code=409,
                    message=(
                        f"Insufficient local stock for product {product.id}: "
                        f"requested={quantity_decimal}, "
                        f"local_available={local_available}"
                    ),
                    details={
                        "product_id": str(product.id),
                        "requested": str(quantity_decimal),
                        "local_available": str(local_available),
                        "supplier_available": str(supplier_available),
                        "reason": "local_inventory_missing",
                    },
                )

            inventory.quantity -= segment.quantity
            session.add(inventory)

            await crud_stock_movement.create_draft(
                session=session,
                data=InventoryStockMovementCreate(
                    movement_type=MovementType.OUTGOING.value,
                    reference_type=ReferenceType.ORDER.value,
                    reference_id=order_id,
                    from_place_id=inventory.place_id,
                    to_place_id=None,
                    product_id=product.id,
                    quantity=segment.quantity,
                    unit_cost=product.base_price,
                    reason="Local stock reserved during checkout (segment=local)",
                    status=MovementStatus.PENDING.value,
                ),
                user=current_user,
            )
            continue

        product.supplier_quantity -= segment.quantity
        session.add(product)

        supplier_reason = (
            f"Supplier stock reserved during checkout (segment={segment.segment.value})"
        )

        await crud_stock_movement.create_draft(
            session=session,
            data=InventoryStockMovementCreate(
                movement_type=MovementType.OUTGOING.value,
                reference_type=ReferenceType.ORDER.value,
                reference_id=order_id,
                from_place_id=None,
                to_place_id=None,
                product_id=product.id,
                quantity=segment.quantity,
                unit_cost=product.base_price,
                reason=supplier_reason,
                status=MovementStatus.PENDING.value,
            ),
            user=current_user,
        )

    return segments


router = APIRouter(prefix="/cart", tags=["cart"])


def _build_cart_detail(cart: Cart, items: list[CartItem]) -> CartDetailPublic:
    """Build cart detail."""
    item_details = [
        CartItemDetail(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=quantize_amount(item.unit_price * item.quantity, cart.currency),
        )
        for item in items
    ]

    return CartDetailPublic(
        id=cart.id,
        user_id=cart.user_id,
        currency=cart.currency,
        total_amount=cart.total_amount,
        is_checked_out=cart.is_checked_out,
        items=item_details,
    )


async def _get_active_product_or_404(
    session: SessionDep,
    *,
    product_id: uuid.UUID,
) -> Product:
    """Get active product or 404."""
    product = await session.get(Product, product_id)
    if product is None or not product.is_active or not product.is_admin_active:
        raise AppError(
            code="cart.product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        )

    if getattr(product, "has_variants", False):
        # The parent is the storefront entry; only a chosen variant is sold.
        raise AppError(
            code="cart.product.has_variants",
            status_code=409,
            message=f"Product '{product_id}' has variants: choose one",
            details={"product_id": str(product_id)},
        )
    # A product whose customs rate or weight is missing prices below cost
    # (see services/publication.py). Refuse the sale rather than honour a
    # price we know to be wrong — this also covers carts filled before the
    # product lost its rate.
    blockers = await publication_blockers(session, product)
    if blockers:
        raise AppError(
            code="cart.product.not_purchasable",
            status_code=409,
            message=f"Product '{product_id}' is not available for sale",
            details={"product_id": str(product_id), "blockers": blockers},
        )

    product.base_price = await calculate_sale_price(session, product)
    return product


@router.get("/me", response_model=CartDetailPublic)
async def get_my_cart(
    session: SessionDep,
    current_user: CurrentUser,
) -> CartDetailPublic:
    """Get my cart."""
    cart = await crud_cart.get_or_create_active_cart(
        session=session,
        user_id=current_user.id,
    )
    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    return _build_cart_detail(cart, items)


@router.post(
    "/items",
    response_model=CartDetailPublic,
    status_code=status.HTTP_201_CREATED,
)
async def add_cart_item(
    session: SessionDep,
    current_user: CurrentUser,
    payload: CartItemAddRequest,
) -> CartDetailPublic:
    """Execute add cart item."""
    cart = await crud_cart.get_or_create_active_cart(
        session=session,
        user_id=current_user.id,
    )
    # Capture before add_or_increment/sync_total commit (which expire `cart`) —
    # re-reading cart.id from an expired instance triggers a sync lazy-load
    # (MissingGreenlet) in the async session.
    cart_id = cart.id
    product = await _get_active_product_or_404(session, product_id=payload.product_id)

    await crud_cart_item.add_or_increment(
        session=session,
        cart_id=cart_id,
        product=product,
        quantity=payload.quantity,
    )
    await crud_cart.sync_total(session=session, cart_id=cart_id)
    await session.refresh(cart)

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart_id)
    return _build_cart_detail(cart, items)


@router.patch("/items/{item_id}", response_model=CartDetailPublic)
async def update_cart_item_quantity(
    session: SessionDep,
    current_user: CurrentUser,
    item_id: uuid.UUID,
    payload: CartItemQuantityUpdateRequest,
) -> CartDetailPublic:
    """Update cart item quantity."""
    item = await crud_cart_item.get_active_item_for_user(
        session=session,
        item_id=item_id,
        user_id=current_user.id,
    )
    if item is None:
        raise AppError(
            code="cart.item.not_found",
            status_code=404,
            message=f"Cart item '{item_id}' not found",
            details={"item_id": str(item_id)},
        )

    await crud_cart_item.update_quantity(
        session=session,
        item=item,
        quantity=payload.quantity,
    )
    await crud_cart.sync_total(session=session, cart_id=item.cart_id)

    cart = await session.get(Cart, item.cart_id)
    if cart is None:
        raise AppError(
            code="cart.not_found",
            status_code=404,
            message=f"Cart '{item.cart_id}' not found",
            details={"cart_id": str(item.cart_id)},
        )

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    return _build_cart_detail(cart, items)


@router.delete("/items/{item_id}", response_model=CartDetailPublic)
async def remove_cart_item(
    session: SessionDep,
    current_user: CurrentUser,
    item_id: uuid.UUID,
) -> CartDetailPublic:
    """Remove cart item."""
    item = await crud_cart_item.get_active_item_for_user(
        session=session,
        item_id=item_id,
        user_id=current_user.id,
    )
    if item is None:
        raise AppError(
            code="cart.item.not_found",
            status_code=404,
            message=f"Cart item '{item_id}' not found",
            details={"item_id": str(item_id)},
        )

    await crud_cart_item.deactivate_item(session=session, item=item)
    await crud_cart.sync_total(session=session, cart_id=item.cart_id)

    cart = await session.get(Cart, item.cart_id)
    if cart is None:
        raise AppError(
            code="cart.not_found",
            status_code=404,
            message=f"Cart '{item.cart_id}' not found",
            details={"cart_id": str(item.cart_id)},
        )

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    return _build_cart_detail(cart, items)


@router.put("/items", response_model=CartDetailPublic)
async def replace_my_cart_items(
    session: SessionDep,
    current_user: CurrentUser,
    payload: CartReplaceRequest,
) -> CartDetailPublic:
    """Install a whole cart content in one transaction.

    The storefront cart lives in the browser; mirroring it into the backend
    used to mean a DELETE followed by one POST per line. That sequence is not
    atomic: a failure in the middle left a truncated server cart, which the
    checkout then ordered as if it were complete. It was not a merge either —
    the clear destroyed whatever the account already had, so a cart built on
    one device was wiped by a checkout started on another.

    Products are resolved and validated first (existence, availability,
    sellability, current price), then written in a single transaction.
    """
    # Merge repeats before touching anything: two lines for the same product
    # would otherwise violate the one-row-per-product invariant of the cart.
    merged: dict[uuid.UUID, int] = {}
    for entry in payload.items:
        merged[entry.product_id] = merged.get(entry.product_id, 0) + entry.quantity

    # Resolve the cart BEFORE the products: get_or_create_active_cart commits,
    # and a commit expires every loaded instance. Resolving products first
    # would leave them expired — and, worse, would discard the sale price
    # _get_active_product_or_404 just computed onto product.base_price.
    cart = await crud_cart.get_or_create_active_cart(
        session=session,
        user_id=current_user.id,
    )
    # Capture before replace/sync_total commit (which expire `cart`) — reading
    # cart.id from an expired instance triggers a sync lazy-load (MissingGreenlet).
    cart_id = cart.id

    entries: list[tuple[Product, int]] = []
    for product_id, quantity in merged.items():
        product = await _get_active_product_or_404(session, product_id=product_id)
        entries.append((product, quantity))

    await crud_cart_item.replace_cart_items(
        session=session,
        cart_id=cart_id,
        entries=entries,
    )
    await crud_cart.sync_total(session=session, cart_id=cart_id)
    await session.refresh(cart)

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart_id)
    return _build_cart_detail(cart, items)


@router.delete("/items", response_model=CartDetailPublic)
async def clear_my_cart(
    session: SessionDep,
    current_user: CurrentUser,
) -> CartDetailPublic:
    """Execute clear my cart."""
    cart = await crud_cart.get_or_create_active_cart(
        session=session,
        user_id=current_user.id,
    )
    # Capture the id before clear_cart/sync_total commit (which expire `cart`);
    # re-reading cart.id from an expired instance triggers a sync lazy-load
    # (MissingGreenlet) in the async session.
    cart_id = cart.id

    await crud_cart_item.clear_cart(session=session, cart_id=cart_id)
    await crud_cart.sync_total(session=session, cart_id=cart_id)
    await session.refresh(cart)

    return _build_cart_detail(cart, [])


def _snapshot_text_value(
    item: dict[str, str | None],
    key: str,
    *,
    fallback: str = "n/a",
) -> str:
    """Get snapshot value normalized for text rendering."""
    value = item.get(key)
    if value is None:
        return fallback

    normalized = str(value).strip()
    if not normalized:
        return fallback
    return normalized


def _quote_items(
    item_snapshots: list[dict[str, str | None]],
) -> list[dict[str, str]]:
    """Normalise cart snapshots into template-friendly item rows."""
    return [
        {
            "product_name": _snapshot_text_value(
                item, "product_name", fallback="Produit"
            ),
            "quantity": _snapshot_text_value(item, "quantity", fallback="0"),
            "unit_price": _snapshot_text_value(item, "unit_price", fallback="0.00"),
            "line_total": _snapshot_text_value(item, "line_total", fallback="0.00"),
            "image_url": _snapshot_text_value(item, "image_url", fallback=""),
        }
        for item in item_snapshots
    ]


def _render_quote_email(
    *,
    subtitle: str,
    contact: str,
    summary: list[tuple[str, str]],
    currency: str,
    item_snapshots: list[dict[str, str | None]],
    subtotal_amount: Decimal,
) -> tuple[str, str, str]:
    """Render a quote-request support email via the shared email layout."""
    email = render_email(
        "quote_request",
        subtitle=subtitle,
        contact=contact,
        item_count=len(item_snapshots),
        summary=[{"label": label, "value": value} for label, value in summary],
        items=_quote_items(item_snapshots),
        currency=currency.strip().upper() or settings.REFERENCE_CURRENCY,
        subtotal=str(subtotal_amount),
        shop_name=getattr(settings, "SHOP_NAME", "Natimai"),
    )
    return email.subject, email.text, email.html


def _format_quote_support_email(
    *,
    current_user: User,
    currency: str,
    item_snapshots: list[dict[str, str | None]],
    subtotal_amount: Decimal,
    shipping_address: str | None,
    notes: str | None,
) -> tuple[str, str, str]:
    """Build subject and body for support quote request emails."""
    return _render_quote_email(
        subtitle="Demande transmise depuis le panier client.",
        contact=str(current_user.email),
        summary=[
            ("Utilisateur", str(current_user.id)),
            ("Email", str(current_user.email)),
            ("Nom", current_user.full_name or "n/a"),
            ("Téléphone", current_user.phone or "n/a"),
            ("Adresse de livraison", shipping_address or "n/a"),
            ("Notes", notes or "n/a"),
        ],
        currency=currency,
        item_snapshots=item_snapshots,
        subtotal_amount=subtotal_amount,
    )


def _format_guest_quote_support_email(
    *,
    customer_email: str,
    customer_name: str | None,
    customer_phone: str | None,
    currency: str,
    item_snapshots: list[dict[str, str | None]],
    subtotal_amount: Decimal,
    shipping_address: str | None,
    notes: str | None,
) -> tuple[str, str, str]:
    """Build subject and body for guest quote request emails."""
    return _render_quote_email(
        subtitle="Demande transmise depuis le panier public.",
        contact=customer_email,
        summary=[
            ("Email", customer_email),
            ("Nom", customer_name or "n/a"),
            ("Téléphone", customer_phone or "n/a"),
            ("Adresse de livraison", shipping_address or "n/a"),
            ("Notes", notes or "n/a"),
        ],
        currency=currency,
        item_snapshots=item_snapshots,
        subtotal_amount=subtotal_amount,
    )


async def _send_quote_support_email(
    *,
    recipient: str,
    subject: str,
    text: str,
    html: str | None,
    metadata: dict[str, Any],
) -> bool:
    """Send support email for a quote request."""
    provider_code = settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
    try:
        provider = get_notification_provider(provider_code)
    except UnknownNotificationProviderError:
        provider = get_notification_provider("noop")

    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient=recipient,
            subject=subject,
            text=text,
            html=html,
            metadata=metadata,
        )
    )
    if not result.delivered:
        logger.warning("Quote request email delivery failed: %s", result.error)
    return result.delivered


@router.post(
    "/quote-request",
    response_model=QuoteRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quote_request(
    session: SessionDep,
    current_user: CurrentUser,
    payload: QuoteRequestSubmit,
) -> QuoteRequestResponse:
    """Create a quote request from the active cart and notify support."""
    support_email = (settings.EMAIL_SUPPORT or "").strip()
    if not support_email:
        raise AppError(
            code="cart.quote.unavailable",
            status_code=503,
            message="EMAIL_SUPPORT is not configured",
            details={"setting": "EMAIL_SUPPORT"},
        )

    cart = await crud_cart.get_active_cart_by_user(
        session=session,
        user_id=current_user.id,
    )
    if cart is None:
        raise AppError(
            code="cart.active.not_found",
            status_code=400,
            message="No active cart found",
            details={"user_id": str(current_user.id)},
        )

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    if not items:
        raise AppError(
            code="cart.empty",
            status_code=400,
            message="Cart is empty",
            details={"cart_id": str(cart.id)},
        )

    item_snapshots: list[dict[str, str | None]] = []
    subtotal_amount = Decimal("0.00")
    for item in items:
        product = await _get_active_product_or_404(session, product_id=item.product_id)
        line_total = quantize_amount(item.unit_price * item.quantity, cart.currency)
        subtotal_amount += line_total
        item_snapshots.append(
            {
                "product_id": str(item.product_id),
                "product_name": product.name,
                "image_url": getattr(product, "image_url", None)
                or getattr(product, "supplier_image_url", None),
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "line_total": str(line_total),
            }
        )

    subject, email_body, email_html = _format_quote_support_email(
        current_user=current_user,
        currency=cart.currency,
        item_snapshots=item_snapshots,
        subtotal_amount=subtotal_amount,
        shipping_address=payload.shipping_address,
        notes=payload.notes,
    )

    quote_request = await crud_quote_request.create_draft(
        session=session,
        data=QuoteRequestCreate(
            user_id=current_user.id,
            cart_id=cart.id,
            email=str(current_user.email),
            phone=current_user.phone,
            full_name=current_user.full_name,
            shipping_address=payload.shipping_address,
            notes=payload.notes,
            status=QuoteRequestStatus.REQUESTED,
            items_snapshot={
                "currency": cart.currency,
                "subtotal_amount": str(subtotal_amount),
                "items": item_snapshots,
            },
        ),
        user=current_user,
    )

    email_delivered = await _send_quote_support_email(
        recipient=support_email,
        subject=subject,
        text=email_body,
        html=email_html,
        metadata={
            "event_type": "quote.requested",
            "quote_request_id": str(quote_request.id),
            "user_id": str(current_user.id),
        },
    )

    if not email_delivered:
        quote_request.status = QuoteRequestStatus.EMAIL_FAILED
        session.add(quote_request)

    await session.commit()
    await session.refresh(quote_request)

    return QuoteRequestResponse(
        quote_request_id=quote_request.id,
        email_delivered=email_delivered,
        message=(
            "Quote request created and support notified"
            if email_delivered
            else "Quote request created but support email failed"
        ),
    )


@router.post(
    "/guest-quote-request",
    response_model=GuestQuoteRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_guest_quote_request(
    payload: GuestQuoteRequestSubmit,
    session: SessionDep,
) -> GuestQuoteRequestResponse:
    """Enregistrer puis transmettre une demande de devis d'un visiteur.

    La demande est **persistée avant l'envoi** : auparavant elle n'existait que
    sous forme d'email, et un échec d'envoi la perdait définitivement alors que
    l'endpoint répondait 201. Le back-office (A11) est désormais le filet.
    """
    support_email = (settings.EMAIL_SUPPORT or "").strip()
    if not support_email:
        raise AppError(
            code="cart.quote.unavailable",
            status_code=503,
            message="EMAIL_SUPPORT is not configured",
            details={"setting": "EMAIL_SUPPORT"},
        )

    customer_email = payload.customer_email.strip().lower()
    if not customer_email or "@" not in customer_email:
        raise AppError(
            code="cart.quote.invalid_email",
            status_code=400,
            message="customer_email is invalid",
            details={"field": "customer_email"},
        )

    if not payload.items:
        raise AppError(
            code="cart.empty",
            status_code=400,
            message="Cart is empty",
            details={"reason": "guest_payload_items_empty"},
        )

    currency = (
        payload.currency or settings.REFERENCE_CURRENCY
    ).strip().upper() or settings.REFERENCE_CURRENCY

    item_snapshots: list[dict[str, str | None]] = []
    subtotal_amount = Decimal("0.00")
    for item in payload.items:
        unit_price = quantize_amount(item.unit_price, currency)
        line_total = quantize_amount(unit_price * item.quantity, currency)
        subtotal_amount += line_total
        item_snapshots.append(
            {
                "product_id": str(item.product_id) if item.product_id else "n/a",
                "product_name": item.product_name,
                "image_url": item.product_image_url,
                "quantity": str(item.quantity),
                "unit_price": str(unit_price),
                "line_total": str(line_total),
            }
        )

    subject, email_body, email_html = _format_guest_quote_support_email(
        customer_email=customer_email,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        currency=currency,
        item_snapshots=item_snapshots,
        subtotal_amount=subtotal_amount,
        shipping_address=payload.shipping_address,
        notes=payload.notes,
    )

    # Persistée d'abord, et committée : si l'envoi échoue ensuite, la demande
    # reste consultable dans le back-office avec le statut qui le dit.
    quote_request = await crud_quote_request.create_draft(
        session=session,
        data=QuoteRequestCreate(
            user_id=None,
            cart_id=None,
            email=customer_email,
            phone=payload.customer_phone,
            full_name=payload.customer_name,
            shipping_address=payload.shipping_address,
            notes=payload.notes,
            status=QuoteRequestStatus.REQUESTED,
            items_snapshot={
                "currency": currency,
                "subtotal_amount": str(subtotal_amount),
                "items": item_snapshots,
            },
        ),
        user=None,
    )
    # Capturé AVANT le commit : celui-ci expire l'instance, et relire un
    # attribut expiré depuis du code asynchrone lève MissingGreenlet.
    quote_request_id = quote_request.id
    await session.commit()

    email_delivered = await _send_quote_support_email(
        recipient=support_email,
        subject=subject,
        text=email_body,
        html=email_html,
        metadata={
            "event_type": "quote.requested.guest",
            "quote_request_id": str(quote_request_id),
            "customer_email": customer_email,
            "item_count": len(item_snapshots),
        },
    )

    if not email_delivered:
        # Rechargée plutôt que réutilisée, pour la même raison.
        failed = await session.get(QuoteRequest, quote_request_id)
        if failed is not None:
            failed.status = QuoteRequestStatus.EMAIL_FAILED
            session.add(failed)
            await session.commit()

    return GuestQuoteRequestResponse(
        email_delivered=email_delivered,
        message=(
            "Guest quote request sent to support"
            if email_delivered
            else "Guest quote request received but support email failed"
        ),
    )


@dataclass(frozen=True)
class CheckoutQuote:
    """Everything the checkout bills, computed once and shared with the quote
    endpoint so the recap the customer reads is the amount debited."""

    currency: str
    declared_value: Decimal
    total_weight_kg: Decimal
    last_leg_route: ShippingRoute | None
    selected_routes: list[ShippingRoute]
    priced_routes: list[ShippingRoute]
    declaration_fees: list[CustomsDeclarationFee]
    shipping_cost_summary: ShippingCostSummary | None
    shipping_cost_breakdown: dict[str, Any] | None
    subtotal_amount: Decimal
    shipping_fee_amount: Decimal
    payment_fee_amount: Decimal
    total_fees_amount: Decimal
    total_amount: Decimal
    #: Promo code applied (validated and priced server-side), if any.
    discount: AppliedDiscount | None = None

    @property
    def discount_amount(self) -> Decimal:
        """What the promo code takes off the lines (0 without one)."""
        return self.discount.amount if self.discount is not None else Decimal("0.00")

    @property
    def customs_declaration_fee_total(self) -> Decimal:
        """Part of the shipping fee owed to the customs declaration."""
        if self.shipping_cost_summary is None:
            return Decimal("0.00")
        return quantize_amount(
            sum(
                (
                    fee.amount
                    for fee in self.shipping_cost_summary.customs_declaration_fees
                ),
                Decimal("0"),
            ),
            self.currency,
        )

    @property
    def free_shipping_applied(self) -> bool:
        """The franco zeroed the last leg."""
        return bool(
            self.last_leg_route is not None
            and self.shipping_cost_summary is not None
            and any(
                segment.route_id == self.last_leg_route.id
                and segment.free_shipping_applied
                for segment in self.shipping_cost_summary.breakdown
            )
        )

    @property
    def shipping_eta_days(self) -> int | None:
        """Summed ETA of the priced legs, when every leg has one."""
        return (
            self.shipping_cost_summary.eta_days
            if self.shipping_cost_summary is not None
            else None
        )


async def _quote_checkout(
    session: SessionDep,
    *,
    user_id: uuid.UUID,
    currency: str,
    items: list[CartItem],
    products_by_id: dict[uuid.UUID, Product],
    shipping_address_id: uuid.UUID | None,
    delivery_type: str | None,
    payment_method_id: uuid.UUID | None,
    shipping_route_ids: list[uuid.UUID] | None = None,
    shipping_preference: CheckoutShippingPreference | None = None,
    shipping_fee_fallback: Decimal | None = None,
    discount: AppliedDiscount | None = None,
) -> CheckoutQuote:
    """Resolve the routes and the amounts of a checkout (no writes).

    One function for the quote (``GET /cart/me/checkout-quote``) and the
    order (``POST /cart/checkout``): the storefront recap can only differ from
    the debited amount if they diverge, so they cannot.

    Raises ``checkout.delivery_type.unavailable`` when the chosen delivery
    mode does not serve the address' destination.
    """
    declared_value, total_weight_kg = _compute_checkout_declared_value_and_weight(
        items=items,
        products_by_id=products_by_id,
    )

    # The last leg (zone C) is the route behind the customer's delivery_type. It
    # must serve the shipping address' destination (île → archipel → pays) or be
    # always_available; a delivery_type that does not resolve is rejected
    # instead of silently skipping the tariff.
    checkout_address = await _load_user_address(
        session, user_id=user_id, address_id=shipping_address_id
    )
    destination_chain = await _destination_chain_for_address(
        session, address=checkout_address
    )
    last_leg_route = await _resolve_last_leg_route(
        session,
        delivery_type=delivery_type,
        destination_chain=destination_chain,
    )
    if delivery_type and last_leg_route is None:
        raise AppError(
            code="checkout.delivery_type.unavailable",
            status_code=400,
            message=(
                f"Delivery mode '{delivery_type}' is not available for this destination"
            ),
            details={
                "delivery_type": delivery_type,
                "shipping_address_id": (
                    str(shipping_address_id) if shipping_address_id else None
                ),
            },
        )

    # Explicit route ids (API clients) win; otherwise a preference may pick the
    # upstream legs — but never a second last leg when delivery_type already
    # names it (that used to bill both and track the wrong carrier).
    selected_routes = await _resolve_selected_checkout_routes(
        session=session,
        shipping_route_ids=list(shipping_route_ids or []),
    )
    if not selected_routes:
        selected_routes = await _select_checkout_routes_by_preference(
            session=session,
            preference=shipping_preference,
            total_weight_kg=total_weight_kg,
            declared_value=declared_value,
            currency=currency,
            include_customer_routes=last_leg_route is None,
        )

    # Price the import/intermediate legs together with the chosen last leg.
    priced_routes = list(selected_routes)
    if last_leg_route is not None and all(
        route.id != last_leg_route.id for route in priced_routes
    ):
        priced_routes.append(last_leg_route)

    # Per-declaration customs charges: once per shipment, whatever the routing
    # and the number of lines (F3) — none when nothing crosses customs.
    declaration_fees = await _customs_declaration_fees(
        session, list(products_by_id.values())
    )

    shipping_cost_summary: ShippingCostSummary | None = None
    shipping_cost_breakdown: dict[str, Any] | None = None
    shipping_fee_input = shipping_fee_fallback or Decimal("0.00")
    if priced_routes or declaration_fees:
        shipping_cost_summary = calculate_shipping_for_routes(
            routes=priced_routes,
            total_weight_kg=total_weight_kg,
            declared_value=declared_value,
            currency=currency,
            customs_declaration_fees=declaration_fees,
        )
        shipping_fee_input = shipping_cost_summary.total_fee
        shipping_cost_breakdown = serialize_shipping_cost_summary(shipping_cost_summary)

    # The fee belongs to the payment method, never to the caller.
    resolved_payment_fee = await _resolve_payment_fee(
        session,
        payment_method_id=payment_method_id,
        currency=currency,
    )
    (
        subtotal_amount,
        shipping_fee_amount,
        payment_fee_amount,
        total_fees_amount,
        total_amount,
    ) = _snapshot_checkout_amounts(
        items=items,
        currency=currency,
        shipping_fee_amount=shipping_fee_input,
        payment_fee_amount=resolved_payment_fee,
        discount_amount=discount.amount if discount is not None else Decimal("0.00"),
    )

    return CheckoutQuote(
        currency=currency,
        declared_value=declared_value,
        total_weight_kg=total_weight_kg,
        last_leg_route=last_leg_route,
        selected_routes=selected_routes,
        priced_routes=priced_routes,
        declaration_fees=declaration_fees,
        shipping_cost_summary=shipping_cost_summary,
        shipping_cost_breakdown=shipping_cost_breakdown,
        subtotal_amount=subtotal_amount,
        shipping_fee_amount=shipping_fee_amount,
        payment_fee_amount=payment_fee_amount,
        total_fees_amount=total_fees_amount,
        total_amount=total_amount,
        discount=discount,
    )


async def _resolve_checkout_discount(
    session: SessionDep,
    *,
    code: str | None,
    user_id: uuid.UUID,
    items: list[CartItem],
    products_by_id: dict[uuid.UUID, Product],
    currency: str,
    strict: bool,
) -> tuple[AppliedDiscount | None, str | None]:
    """Price the promo code for this cart.

    ``strict`` (the checkout) turns a refusal into a 400; the quote keeps the
    reason as text so the recap can say why the code was not applied.
    """
    if not code or not code.strip():
        return None, None
    try:
        applied = await resolve_coupon(
            session,
            code=code,
            user_id=user_id,
            items=items,
            products_by_id=products_by_id,
            currency=currency,
        )
    except DiscountRefused as exc:
        if strict:
            raise AppError(
                code="checkout.discount.refused",
                status_code=400,
                message=exc.message,
                details={"discount_code": code, "reason": exc.reason},
            ) from exc
        return None, exc.message
    return applied, None


@router.get("/me/checkout-quote", response_model=CheckoutQuoteResponse)
async def get_checkout_quote(
    session: SessionDep,
    current_user: CurrentUser,
    address_id: uuid.UUID | None = Query(
        default=None, description="Shipping address (must belong to the user)"
    ),
    delivery_type: str | None = Query(
        default=None, description="Chosen last-leg delivery mode"
    ),
    payment_method_id: uuid.UUID | None = Query(
        default=None, description="Chosen payment method (its fee is added)"
    ),
    discount_code: str | None = Query(
        default=None, max_length=50, description="Promo code to price"
    ),
) -> CheckoutQuoteResponse:
    """The amounts ``POST /cart/checkout`` will bill for the current backend
    cart and these choices — same computation, so the recap is the debit.

    Read-only: nothing is reserved, revalidated or written. An empty cart
    quotes zero rather than failing, so the recap can render early.
    """
    user_id = current_user.id
    cart = await crud_cart.get_active_cart_by_user(session=session, user_id=user_id)
    currency = cart.currency if cart is not None else settings.REFERENCE_CURRENCY
    zero = quantize_amount(Decimal("0"), currency)
    if cart is None:
        return CheckoutQuoteResponse(
            currency=currency,
            subtotal_amount=zero,
            shipping_fee_amount=zero,
            payment_fee_amount=zero,
            total_fees_amount=zero,
            total_amount=zero,
            delivery_type=delivery_type,
        )

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    products_by_id: dict[uuid.UUID, Product] = {}
    for item in items:
        products_by_id[item.product_id] = await _get_active_product_or_404(
            session, product_id=item.product_id
        )

    applied_discount, discount_error = await _resolve_checkout_discount(
        session,
        code=discount_code,
        user_id=user_id,
        items=items,
        products_by_id=products_by_id,
        currency=currency,
        strict=False,
    )
    quote = await _quote_checkout(
        session,
        user_id=user_id,
        currency=currency,
        items=items,
        products_by_id=products_by_id,
        shipping_address_id=address_id,
        delivery_type=delivery_type,
        payment_method_id=payment_method_id,
        discount=applied_discount,
    )
    return CheckoutQuoteResponse(
        currency=quote.currency,
        subtotal_amount=quote.subtotal_amount,
        shipping_fee_amount=quote.shipping_fee_amount,
        customs_declaration_fee=quote.customs_declaration_fee_total,
        payment_fee_amount=quote.payment_fee_amount,
        total_fees_amount=quote.total_fees_amount,
        discount_code=applied_discount.code if applied_discount else None,
        discount_amount=quote.discount_amount,
        discount_label=applied_discount.label if applied_discount else None,
        discount_error=discount_error,
        total_amount=quote.total_amount,
        delivery_type=delivery_type,
        shipping_eta_days=quote.shipping_eta_days,
        free_shipping_applied=quote.free_shipping_applied,
        shipping_cost_breakdown=quote.shipping_cost_breakdown,
    )


@router.get("/me/last-leg-options", response_model=LastLegOptionsResponse)
async def get_last_leg_options(
    session: SessionDep,
    current_user: CurrentUser,
    address_id: uuid.UUID | None = Query(
        default=None,
        description=(
            "Shipping address whose destination filters the delivery modes "
            "(must belong to the current user). Without it, only "
            "destination-independent modes are returned."
        ),
    ),
) -> LastLegOptionsResponse:
    """Priced last-leg (zone C) delivery options for the current cart.

    Lets the storefront show each delivery mode's price before checkout. Mirrors
    the pricing applied at ``POST /cart/checkout`` (base_price + price_per_kg ×
    billable weight). Only delivery modes whose route serves the address'
    destination appear — plus the always-available ones (in-store pickup...).
    """
    cart = await crud_cart.get_active_cart_by_user(
        session=session, user_id=current_user.id
    )
    if cart is None:
        return LastLegOptionsResponse(currency=settings.REFERENCE_CURRENCY, options=[])

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    products_by_id: dict[uuid.UUID, Product] = {}
    try:
        for item in items:
            products_by_id[item.product_id] = await _get_active_product_or_404(
                session, product_id=item.product_id
            )
    except AppError:
        # A cart line is no longer purchasable; no quote to show (checkout will
        # surface the real error). Return no priced options rather than 404.
        return LastLegOptionsResponse(currency=cart.currency, options=[])

    declared_value, total_weight_kg = _compute_checkout_declared_value_and_weight(
        items=items,
        products_by_id=products_by_id,
    )

    address = await _load_user_address(
        session, user_id=current_user.id, address_id=address_id
    )
    destination_chain = await _destination_chain_for_address(session, address=address)

    # Delivery modes are driven by the admin's configured last-leg routes, not a
    # fixed enum: any mode whose route serves this destination appears.
    candidates = await resolve_last_leg_candidates(
        session, destination_chain=destination_chain
    )

    # Shown next to the delivery modes so the customs charge is not a surprise
    # discovered on the payment page (it is billed once per shipment, F3).
    declaration_fee_total = sum(
        (
            fee.amount
            for fee in await _customs_declaration_fees(
                session, list(products_by_id.values())
            )
        ),
        Decimal("0.00"),
    )

    options: list[LastLegOption] = []
    for mode in sorted(candidates):
        route = candidates[mode].route
        summary = calculate_shipping_for_routes(
            routes=[route],
            total_weight_kg=total_weight_kg,
            declared_value=declared_value,
            currency=cart.currency,
        )
        options.append(
            LastLegOption(
                delivery_type=mode,
                label=route.customer_label,
                amount=summary.total_fee,
                currency=cart.currency,
                eta_days=route.eta_days,
                route_name=route.name,
            )
        )

    return LastLegOptionsResponse(
        currency=cart.currency,
        options=options,
        customs_declaration_fee=quantize_amount(declaration_fee_total, cart.currency),
    )


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def checkout_my_cart(
    session: SessionDep,
    current_user: CurrentUser,
    payload: CheckoutRequest,
) -> CheckoutResponse:
    """Execute checkout my cart."""
    checkout_started = perf_counter()
    # session.commit() below expires every instance bound to the session,
    # including current_user. Capture the id up-front so the post-commit logging
    # and error paths don't trigger a sync lazy-load (MissingGreenlet).
    user_id = current_user.id
    cart = await crud_cart.get_active_cart_by_user(
        session=session,
        user_id=user_id,
    )
    if cart is None:
        raise AppError(
            code="cart.active.not_found",
            status_code=400,
            message="No active cart found",
            details={"user_id": str(current_user.id)},
        )

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    if not items:
        raise AppError(
            code="cart.empty",
            status_code=400,
            message="Cart is empty",
            details={"cart_id": str(cart.id)},
        )

    products_by_id: dict[uuid.UUID, Product] = {}
    for item in items:
        product = await _get_active_product_or_404(
            session,
            product_id=item.product_id,
        )
        products_by_id[item.product_id] = product

    # Ask the supplier what it actually has, rather than trusting a snapshot
    # that can be two hours old. Best-effort: an unreachable supplier leaves
    # the snapshot in place instead of refusing the sale.
    await refresh_supplier_availability(session, list(products_by_id.values()))

    # Server-authoritative amounts: a line whose price moved since it was
    # added stops the checkout (the cart is refreshed so the client sees why).
    await _revalidate_checkout_prices(
        session,
        items=items,
        products_by_id=products_by_id,
        currency=cart.currency,
    )

    applied_discount, _ = await _resolve_checkout_discount(
        session,
        code=payload.discount_code,
        user_id=user_id,
        items=items,
        products_by_id=products_by_id,
        currency=cart.currency,
        strict=True,
    )
    quote = await _quote_checkout(
        session,
        user_id=user_id,
        currency=cart.currency,
        items=items,
        products_by_id=products_by_id,
        shipping_address_id=payload.shipping_address_id,
        delivery_type=payload.delivery_type,
        payment_method_id=payload.payment_method_id,
        shipping_route_ids=payload.shipping_route_ids,
        shipping_preference=payload.shipping_preference,
        shipping_fee_fallback=payload.shipping_fee_amount,
        discount=applied_discount,
    )
    selected_routes = quote.selected_routes
    priced_routes = quote.priced_routes
    last_leg_route = quote.last_leg_route
    shipping_cost_summary = quote.shipping_cost_summary
    shipping_cost_breakdown_payload = quote.shipping_cost_breakdown
    subtotal_amount = quote.subtotal_amount
    shipping_fee_amount = quote.shipping_fee_amount
    payment_fee_amount = quote.payment_fee_amount
    total_fees_amount = quote.total_fees_amount
    total_amount = quote.total_amount

    if total_amount <= 0:
        raise AppError(
            code="cart.total.invalid",
            status_code=400,
            message="Cart total must be > 0",
            details={
                "cart_id": str(cart.id),
                "total_amount": str(total_amount),
                "currency": cart.currency,
            },
        )

    # Acceptation des CGV : refusée ici et pas seulement grisée dans le front,
    # sinon un appel direct à l'API commande sans jamais les accepter.
    if not payload.cgv_accepted:
        raise AppError(
            code="cart.cgv.not_accepted",
            status_code=400,
            message="Les conditions générales de vente doivent être acceptées",
            details={"cart_id": str(cart.id), "cgv_version": settings.CGV_VERSION},
        )
    cgv_accepted_at = datetime.now(timezone.utc)

    try:
        price_group = await resolve_default_price_group(session)

        order_status = await _get_or_create_order_pending_status(session)
        # Human-readable reference allocated up-front (server-side only — the
        # field is not part of OrderCreate, cf. Order.order_number).
        order_number = await allocate_order_number(session)
        order = await crud_order.create_draft(
            session=session,
            data=OrderCreate(
                user_id=current_user.id,
                order_status_id=order_status.id,
                total_amount=total_amount,
                subtotal_amount=subtotal_amount,
                shipping_fee_amount=shipping_fee_amount,
                payment_fee_amount=payment_fee_amount,
                total_fees_amount=total_fees_amount,
                discount_id=applied_discount.discount_id if applied_discount else None,
                discount_code=applied_discount.code if applied_discount else None,
                discount_amount=quote.discount_amount,
                currency=cart.currency,
                shipping_address=payload.shipping_address,
                shipping_cost_breakdown=shipping_cost_breakdown_payload,
                notes=payload.notes,
                delivery_type=payload.delivery_type,
                cgv_accepted_at=cgv_accepted_at,
                cgv_version=settings.CGV_VERSION,
            ),
            user=current_user,
        )
        order.order_number = order_number
        session.add(order)

        # Take the use now, inside the transaction: a refusal (the last use
        # just went to someone else) rolls the whole order back.
        if applied_discount is not None:
            try:
                await consume_coupon(session, discount_id=applied_discount.discount_id)
            except DiscountRefused as exc:
                raise AppError(
                    code="checkout.discount.refused",
                    status_code=409,
                    message=exc.message,
                    details={
                        "discount_code": applied_discount.code,
                        "reason": exc.reason,
                    },
                ) from exc
        line_discounts = applied_discount.line_amounts if applied_discount else {}

        # Keyed by (segment, origin place) so each distinct origin (own warehouse,
        # supplier A, supplier B…) gets its own tracking with its own first leg.
        segment_totals: dict[tuple[FulfillmentSegment, uuid.UUID | None], Decimal] = {}

        for item in items:
            product = products_by_id[item.product_id]
            resolved_tax_rate = await resolve_tax_rate(session, product)
            # Snapshot the *effective* rate: it may come from the category, in
            # which case the product column is NULL and would freeze a wrong 0 —
            # and it is 0 for a domestic origin, whatever the category says.
            resolved_customs_rate_pct = await resolve_effective_customs_rate_pct(
                session, product
            )

            line_segments = await _reserve_stock_for_checkout(
                session=session,
                order_id=order.id,
                product=product,
                quantity=item.quantity,
                current_user=current_user,
            )
            line_segments = line_segments or []

            for segment in line_segments:
                key = (segment.segment, segment.origin_place_id)
                segment_totals[key] = (
                    segment_totals.get(key, Decimal("0.00")) + segment.quantity
                )

            line_notes = _format_fulfillment_segments_note(line_segments or [])

            await crud_order_line.create_draft(
                session=session,
                data=OrderLineCreate(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    discount_amount=line_discounts.get(item.id, Decimal("0.00")),
                    notes=line_notes,
                    tax_rate_id=(
                        resolved_tax_rate.id if resolved_tax_rate is not None else None
                    ),
                    cost_amount_snapshot=getattr(product, "cost_amount", None),
                    cost_currency_snapshot=getattr(product, "cost_currency", None)
                    or settings.REFERENCE_CURRENCY,
                    fx_rate_used=getattr(item, "fx_rate_used", None),
                    customs_rate_pct_snapshot=resolved_customs_rate_pct,
                    margin_rate_pct_snapshot=getattr(
                        price_group,
                        "margin_rate_pct",
                        None,
                    ),
                    price_group_id_snapshot=getattr(price_group, "id", None),
                ),
                user=current_user,
            )

        if selected_routes:
            # The journey ends on the chosen last leg (once), whatever the
            # explicit / preference-selected upstream legs.
            tracking_routes = list(selected_routes)
            if last_leg_route is not None and all(
                route.id != last_leg_route.id for route in tracking_routes
            ):
                tracking_routes.append(last_leg_route)
            try:
                await _link_selected_routes_to_tracking(
                    session=session,
                    order_id=order.id,
                    current_user=current_user,
                    shipping_address=payload.shipping_address,
                    shipping_address_id=payload.shipping_address_id,
                    selected_routes=tracking_routes,
                )
            except Exception as tracking_exc:
                log_structured_event(
                    logger,
                    level="warning",
                    event="checkout_selected_routes_tracking_linkage_failed",
                    order_id=order.id,
                    error=str(tracking_exc),
                )
        elif segment_totals:
            try:
                await _link_fulfillment_segments_to_tracking(
                    session=session,
                    order_id=order.id,
                    current_user=current_user,
                    shipping_address=payload.shipping_address,
                    shipping_address_id=payload.shipping_address_id,
                    segment_totals=segment_totals,
                    last_leg_route=last_leg_route,
                )
            except Exception as tracking_exc:
                log_structured_event(
                    logger,
                    level="warning",
                    event="checkout_tracking_linkage_failed",
                    order_id=order.id,
                    error=str(tracking_exc),
                )

        payment_init: PaymentInitiationResult | None = None
        if payload.payment_method_id is not None:
            # Single-payment flow: create the payment AND run the provider
            # initiation (CB SmartForm / manual / document) in this same
            # transaction. No separate POST /payments/initiate is needed.
            payment_init = await initiate_payment_for_method(
                session,
                payment_method_id=payload.payment_method_id,
                amount=total_amount,
                currency=cart.currency,
                order_id=order.id,
                return_url=payload.return_url,
                metadata=None,
                current_user=current_user,
            )
            payment = payment_init.payment
        else:
            # Backward-compatible fallback: a pending placeholder payment to be
            # initiated later via POST /payments/initiate.
            payment_status = await _get_or_create_payment_pending_status(session)
            payment = await crud_payment.create_draft(
                session=session,
                data=PaymentCreate(
                    amount=total_amount,
                    currency=cart.currency,
                    order_id=order.id,
                    user_id=current_user.id,
                ),
                user=current_user,
            )
            payment.payment_status_id = payment_status.id
            session.add(payment)

        cart.is_checked_out = True
        cart.total_amount = total_amount
        session.add(cart)

        for item in items:
            item.is_active = False
            session.add(item)

        await outbox_registry.publish(
            session=session,
            event_type=EVENT_ORDER_CREATED,
            payload={
                "order_id": str(order.id),
                "order_number": order_number,
                "user_id": str(current_user.id),
                "payment_id": str(payment.id),
                "total_amount": str(total_amount),
                "currency": cart.currency,
                "item_count": len(items),
            },
            correlation_id=order.id,
        )

        # Capture ORM-derived values for the response/log BEFORE the commit
        # expires these instances (post-commit attribute access triggers a sync
        # lazy-load → MissingGreenlet). selected_routes / shipping_cost_summary
        # are not refreshed below, so they must be read here.
        applied_shipping_route_ids = [route.id for route in priced_routes]
        shipping_eta_days = (
            shipping_cost_summary.eta_days if shipping_cost_summary else None
        )
        shipping_carbon_footprint_kg_co2e = (
            shipping_cost_summary.carbon_footprint_kg_co2e
            if shipping_cost_summary
            else None
        )

        await session.commit()

        await session.refresh(order)
        await session.refresh(payment)
        await session.refresh(cart)

        checkout_duration_ms = int((perf_counter() - checkout_started) * 1000)
        observe_checkout_result(
            success=True,
            duration_ms=checkout_duration_ms,
        )
        log_structured_event(
            logger,
            level="info",
            event="checkout_completed",
            order_id=order.id,
            payment_id=payment.id,
            user_id=user_id,
            amount=total_amount,
            currency=cart.currency,
            item_count=len(items),
            duration_ms=checkout_duration_ms,
        )

        return CheckoutResponse(
            order_id=order.id,
            order_number=order.order_number,
            payment_id=payment.id,
            cart_id=cart.id,
            subtotal_amount=subtotal_amount,
            discount_code=applied_discount.code if applied_discount else None,
            discount_amount=quote.discount_amount,
            shipping_fee_amount=shipping_fee_amount,
            payment_fee_amount=payment_fee_amount,
            total_fees_amount=total_fees_amount,
            total_amount=total_amount,
            currency=cart.currency,
            item_count=len(items),
            applied_shipping_route_ids=applied_shipping_route_ids,
            shipping_eta_days=shipping_eta_days,
            shipping_carbon_footprint_kg_co2e=shipping_carbon_footprint_kg_co2e,
            shipping_cost_breakdown=shipping_cost_breakdown_payload,
            provider_code=payment_init.provider_code if payment_init else None,
            provider_reference=(
                payment_init.provider_reference if payment_init else None
            ),
            form_token=payment_init.form_token if payment_init else None,
            server_url=payment_init.server_url if payment_init else None,
            public_key=payment_init.public_key if payment_init else None,
            redirect_url=payment_init.redirect_url if payment_init else None,
            instructions=payment_init.instructions if payment_init else None,
            message="Checkout completed",
        )

    except AppError as exc:
        checkout_duration_ms = int((perf_counter() - checkout_started) * 1000)
        observe_checkout_result(
            success=False,
            duration_ms=checkout_duration_ms,
            error_code=exc.code,
        )
        log_structured_event(
            logger,
            level="warning",
            event="checkout_failed",
            user_id=user_id,
            error_code=exc.code,
            duration_ms=checkout_duration_ms,
        )
        await session.rollback()
        raise
    except Exception as exc:
        checkout_duration_ms = int((perf_counter() - checkout_started) * 1000)
        observe_checkout_result(
            success=False,
            duration_ms=checkout_duration_ms,
            error_code="internal_error",
        )
        log_structured_event(
            logger,
            level="error",
            event="checkout_failed",
            user_id=user_id,
            error_code="internal_error",
            error=str(exc),
            duration_ms=checkout_duration_ms,
        )
        await session.rollback()
        raise AppError(
            code="cart.checkout.failed",
            status_code=500,
            message="Checkout failed",
            details={"reason": type(exc).__name__},
        ) from exc
