import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
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
    CheckoutRequest,
    CheckoutResponse,
    CheckoutShippingPreference,
)
from app.features.cart.models.quote_request import (
    QuoteRequestCreate,
    QuoteRequestResponse,
    QuoteRequestSubmit,
)
from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.inventory.models.stock_movement import (
    InventoryStockMovementCreate,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order import OrderCreate
from app.features.order.models.order_line import OrderLineCreate
from app.features.order.models.order_status import OrderStatus, OrderStatusCreate
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import PaymentCreate
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
)
from app.features.product.models.product import Product
from app.features.product.services.pricing import calculate_sale_price, resolve_tax_rate
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
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
    calculate_shipping_for_routes,
    serialize_shipping_cost_summary,
)
from app.features.user.crud.address import crud_address
from app.features.user.models.address import Address, AddressCreate
from app.features.user.models.user import User
from app.utils.money import quantize_amount

_PENDING_ORDER_STATUS = "Pending"
_PENDING_PAYMENT_STATUS = "Pending"

logger = logging.getLogger(__name__)


class FulfillmentSegment(str, Enum):
    """Represents fulfillment segment."""

    LOCAL = "local"
    SUPPLIER_DIRECT = "supplier_direct"
    CONSOLIDATION_PF = "consolidation_pf"


@dataclass(frozen=True)
class FulfillmentAllocation:
    """Represents fulfillment allocation."""

    segment: FulfillmentSegment
    quantity: Decimal


_FULFILLMENT_SEGMENT_PRIORITY: dict[FulfillmentSegment, int] = {
    FulfillmentSegment.LOCAL: 1,
    FulfillmentSegment.SUPPLIER_DIRECT: 2,
    FulfillmentSegment.CONSOLIDATION_PF: 2,
}


_PF_ADDRESS_MARKERS = (
    "PF",
    "POLYNESIE",
    "TAHITI",
    "PAPEETE",
    "MOOREA",
    "BORA",
    "RANGIROA",
)


def _is_polynesia_shipping_address(shipping_address: str | None) -> bool:
    """Check whether polynesia shipping address."""
    if not shipping_address:
        return True

    normalized_address = shipping_address.upper()
    return any(marker in normalized_address for marker in _PF_ADDRESS_MARKERS)


def _select_supplier_segment(shipping_address: str | None) -> FulfillmentSegment:
    """Execute select supplier segment."""
    if _is_polynesia_shipping_address(shipping_address):
        return FulfillmentSegment.CONSOLIDATION_PF
    return FulfillmentSegment.SUPPLIER_DIRECT


def _plan_checkout_fulfillment_segments(
    *,
    product: Product,
    quantity: int,
    local_available: Decimal,
    supplier_available: Decimal,
    shipping_address: str | None,
) -> list[FulfillmentAllocation]:
    """Execute plan checkout fulfillment segments."""
    requested_quantity = Decimal(quantity)
    total_available = local_available + supplier_available

    if total_available < requested_quantity:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Insufficient stock for product {product.id}: "
                f"requested={requested_quantity}, "
                f"local_available={local_available}, "
                f"supplier_available={supplier_available}"
            ),
        )

    local_to_reserve = min(local_available, requested_quantity)
    supplier_to_reserve = requested_quantity - local_to_reserve

    segments: list[FulfillmentAllocation] = []
    if local_to_reserve > 0:
        segments.append(
            FulfillmentAllocation(
                segment=FulfillmentSegment.LOCAL,
                quantity=local_to_reserve,
            )
        )

    if supplier_to_reserve > 0:
        segments.append(
            FulfillmentAllocation(
                segment=_select_supplier_segment(shipping_address),
                quantity=supplier_to_reserve,
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
        raise HTTPException(
            status_code=400,
            detail=(
                "Unknown or inactive shipping routes: " + ", ".join(missing_route_ids)
            ),
        )

    return [route_by_id[route_id] for route_id in ordered_route_ids]


async def _select_checkout_routes_by_preference(
    session: SessionDep,
    *,
    preference: CheckoutShippingPreference | None,
    total_weight_kg: Decimal,
    declared_value: Decimal,
    currency: str,
) -> list[ShippingRoute]:
    """Execute select checkout routes by preference."""
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
    if intermediary_routes:
        selected_routes.append(min(intermediary_routes, key=sort_key))

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
) -> Address:
    """Execute resolve tracking address for checkout."""
    existing_shipping_addresses = await crud_address.get_by_user_and_type(
        session=session,
        user_id=current_user.id,
        address_type="shipping",
    )

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
    country = chunks[-1] if chunks else "PF"

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


async def _resolve_tracking_route_for_segment(
    session: SessionDep,
    *,
    segment: FulfillmentSegment,
) -> ShippingRoute | None:
    """Execute resolve tracking route for segment."""
    if segment == FulfillmentSegment.CONSOLIDATION_PF:
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
    elif segment == FulfillmentSegment.CONSOLIDATION_PF:
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
    segment_totals: dict[FulfillmentSegment, Decimal],
) -> None:
    """Execute link fulfillment segments to tracking."""
    if not segment_totals:
        return

    shipping_address_record = await _resolve_tracking_address_for_checkout(
        session=session,
        current_user=current_user,
        shipping_address=shipping_address,
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
            _FULFILLMENT_SEGMENT_PRIORITY[item[0]],
            item[0].value,
        ),
    )

    for sequence_order, (segment, quantity) in enumerate(ordered_segments, start=1):
        selected_route = await _resolve_tracking_route_for_segment(
            session=session,
            segment=segment,
        )
        if selected_route is None:
            logger.warning(
                "D2 skipped: no shipping route available for segment=%s order_id=%s",
                segment.value,
                order_id,
            )
            continue

        consolidation_id = None
        if segment == FulfillmentSegment.CONSOLIDATION_PF:
            consolidation = (
                await crud_shipping_route_tracking_consolidation.create_draft(
                    session=session,
                    data=ShippingRouteTrackingConsolidationCreate(
                        route_id=selected_route.id,
                        name=f"PF consolidation {order_id}",
                        consolidation_code=(f"pf-{str(order_id)[:8]}-{sequence_order}"),
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

        await crud_shipping_route_tracking.create_draft(
            session=session,
            data=ShippingRouteTrackingCreate(
                order_id=order_id,
                route_id=selected_route.id,
                status_id=route_tracking_status.id,
                address_id=shipping_address_record.id,
                consolidation_id=consolidation_id,
                selected_at=datetime.now(timezone.utc),
                sequence_order=sequence_order,
                last_status_update=None,
                tracking_ref=None,
                estimated_delivery=None,
                notes=(f"segment={segment.value};quantity={quantity};origin=checkout"),
            ),
            user=current_user,
        )


async def _link_selected_routes_to_tracking(
    session: SessionDep,
    *,
    order_id: uuid.UUID,
    current_user: User,
    shipping_address: str | None,
    selected_routes: list[ShippingRoute],
) -> None:
    """Execute link selected routes to tracking."""
    if not selected_routes:
        return

    shipping_address_record = await _resolve_tracking_address_for_checkout(
        session=session,
        current_user=current_user,
        shipping_address=shipping_address,
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
                notes=(f"origin=checkout_selected_routes;sequence={sequence_order}"),
            ),
            user=current_user,
        )


def _snapshot_checkout_amounts(
    *,
    items: list[CartItem],
    currency: str,
    shipping_fee_amount: Decimal,
    payment_fee_amount: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Execute snapshot checkout amounts."""
    subtotal_amount = sum(
        (item.unit_price * item.quantity for item in items),
        Decimal("0.00"),
    )
    subtotal_amount = quantize_amount(subtotal_amount, currency)

    shipping_fee = quantize_amount(shipping_fee_amount, currency)
    payment_fee = quantize_amount(payment_fee_amount, currency)
    total_fees_amount = quantize_amount(shipping_fee + payment_fee, currency)
    total_amount = quantize_amount(subtotal_amount + total_fees_amount, currency)

    return (
        subtotal_amount,
        shipping_fee,
        payment_fee,
        total_fees_amount,
        total_amount,
    )


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
    shipping_address: str | None = None,
) -> list[FulfillmentAllocation]:
    """Execute reserve stock for checkout."""
    quantity_decimal = Decimal(quantity)
    inventory = await crud_inventory.get_by_product_and_place(
        session=session,
        product_id=product.id,
        place_id=None,
    )

    local_available = inventory.quantity if inventory is not None else Decimal("0.00")
    supplier_available = (
        product.supplier_quantity if product.is_supplier_managed else Decimal("0.00")
    )

    segments = _plan_checkout_fulfillment_segments(
        product=product,
        quantity=quantity,
        local_available=local_available,
        supplier_available=supplier_available,
        shipping_address=shipping_address,
    )

    for segment in segments:
        if segment.segment == FulfillmentSegment.LOCAL:
            if inventory is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Insufficient local stock for product {product.id}: "
                        f"requested={quantity_decimal}, "
                        f"local_available={local_available}"
                    ),
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
        raise HTTPException(status_code=404, detail="Product not found")

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
    product = await _get_active_product_or_404(session, product_id=payload.product_id)

    await crud_cart_item.add_or_increment(
        session=session,
        cart_id=cart.id,
        product=product,
        quantity=payload.quantity,
    )
    await crud_cart.sync_total(session=session, cart_id=cart.id)
    await session.refresh(cart)

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
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
        raise HTTPException(status_code=404, detail="Cart item not found")

    await crud_cart_item.update_quantity(
        session=session,
        item=item,
        quantity=payload.quantity,
    )
    await crud_cart.sync_total(session=session, cart_id=item.cart_id)

    cart = await session.get(Cart, item.cart_id)
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found")

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
        raise HTTPException(status_code=404, detail="Cart item not found")

    await crud_cart_item.deactivate_item(session=session, item=item)
    await crud_cart.sync_total(session=session, cart_id=item.cart_id)

    cart = await session.get(Cart, item.cart_id)
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found")

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
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

    await crud_cart_item.clear_cart(session=session, cart_id=cart.id)
    await crud_cart.sync_total(session=session, cart_id=cart.id)
    await session.refresh(cart)

    return _build_cart_detail(cart, [])


def _format_quote_support_email(
    *,
    current_user: User,
    currency: str,
    item_snapshots: list[dict[str, str]],
    subtotal_amount: Decimal,
    shipping_address: str | None,
    notes: str | None,
) -> tuple[str, str]:
    """Build subject and body for support quote request emails."""
    subject = f"[Quote Request] user={current_user.id} items={len(item_snapshots)}"

    lines = [
        "Nouvelle demande de devis",
        "",
        f"user_id: {current_user.id}",
        f"email: {current_user.email}",
        f"full_name: {current_user.full_name or 'n/a'}",
        f"phone: {current_user.phone or 'n/a'}",
        f"shipping_address: {shipping_address or 'n/a'}",
        f"notes: {notes or 'n/a'}",
        "",
        "Panier:",
    ]

    for item in item_snapshots:
        lines.append(
            "- "
            f"{item['product_name']} "
            f"(qty={item['quantity']}, unit={item['unit_price']} {currency}, "
            f"line_total={item['line_total']} {currency})"
        )

    lines.extend(
        [
            "",
            f"subtotal: {subtotal_amount} {currency}",
        ]
    )

    return subject, "\n".join(lines)


async def _send_quote_support_email(
    *,
    recipient: str,
    subject: str,
    text: str,
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
        raise HTTPException(
            status_code=503,
            detail="EMAIL_SUPPORT is not configured",
        )

    cart = await crud_cart.get_active_cart_by_user(
        session=session,
        user_id=current_user.id,
    )
    if cart is None:
        raise HTTPException(status_code=400, detail="No active cart found")

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    item_snapshots: list[dict[str, str]] = []
    subtotal_amount = Decimal("0.00")
    for item in items:
        product = await _get_active_product_or_404(session, product_id=item.product_id)
        line_total = quantize_amount(item.unit_price * item.quantity, cart.currency)
        subtotal_amount += line_total
        item_snapshots.append(
            {
                "product_id": str(item.product_id),
                "product_name": product.name,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "line_total": str(line_total),
            }
        )

    subject, email_body = _format_quote_support_email(
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
            status="requested",
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
        metadata={
            "event_type": "quote.requested",
            "quote_request_id": str(quote_request.id),
            "user_id": str(current_user.id),
        },
    )

    if not email_delivered:
        quote_request.status = "email_failed"
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
    cart = await crud_cart.get_active_cart_by_user(
        session=session,
        user_id=current_user.id,
    )
    if cart is None:
        raise HTTPException(status_code=400, detail="No active cart found")

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    products_by_id: dict[uuid.UUID, Product] = {}
    for item in items:
        product = await _get_active_product_or_404(
            session,
            product_id=item.product_id,
        )
        products_by_id[item.product_id] = product

    declared_value, total_weight_kg = _compute_checkout_declared_value_and_weight(
        items=items,
        products_by_id=products_by_id,
    )

    selected_routes = await _resolve_selected_checkout_routes(
        session=session,
        shipping_route_ids=payload.shipping_route_ids,
    )
    if not selected_routes:
        selected_routes = await _select_checkout_routes_by_preference(
            session=session,
            preference=payload.shipping_preference,
            total_weight_kg=total_weight_kg,
            declared_value=declared_value,
            currency=cart.currency,
        )

    shipping_cost_summary = None
    shipping_cost_breakdown_payload: dict[str, Any] | None = None
    shipping_fee_input = payload.shipping_fee_amount or Decimal("0.00")
    if selected_routes:
        shipping_cost_summary = calculate_shipping_for_routes(
            routes=selected_routes,
            total_weight_kg=total_weight_kg,
            declared_value=declared_value,
            currency=cart.currency,
        )
        shipping_fee_input = shipping_cost_summary.total_fee
        shipping_cost_breakdown_payload = serialize_shipping_cost_summary(
            shipping_cost_summary
        )

    (
        subtotal_amount,
        shipping_fee_amount,
        payment_fee_amount,
        total_fees_amount,
        total_amount,
    ) = _snapshot_checkout_amounts(
        items=items,
        currency=cart.currency,
        shipping_fee_amount=shipping_fee_input,
        payment_fee_amount=payload.payment_fee_amount,
    )
    if total_amount <= 0:
        raise HTTPException(status_code=400, detail="Cart total must be > 0")

    try:
        order_status = await _get_or_create_order_pending_status(session)
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
                shipping_address=payload.shipping_address,
                shipping_cost_breakdown=shipping_cost_breakdown_payload,
                notes=payload.notes,
            ),
            user=current_user,
        )

        segment_totals: dict[FulfillmentSegment, Decimal] = {}

        for item in items:
            product = products_by_id[item.product_id]
            resolved_tax_rate = await resolve_tax_rate(session, product)

            line_segments = await _reserve_stock_for_checkout(
                session=session,
                order_id=order.id,
                product=product,
                quantity=item.quantity,
                current_user=current_user,
                shipping_address=payload.shipping_address,
            )
            line_segments = line_segments or []

            for segment in line_segments:
                current_total = segment_totals.get(segment.segment, Decimal("0.00"))
                segment_totals[segment.segment] = current_total + segment.quantity

            line_notes = _format_fulfillment_segments_note(line_segments or [])

            await crud_order_line.create_draft(
                session=session,
                data=OrderLineCreate(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    discount_amount=Decimal("0.00"),
                    notes=line_notes,
                    tax_rate_id=(
                        resolved_tax_rate.id if resolved_tax_rate is not None else None
                    ),
                ),
                user=current_user,
            )

        if selected_routes:
            try:
                await _link_selected_routes_to_tracking(
                    session=session,
                    order_id=order.id,
                    current_user=current_user,
                    shipping_address=payload.shipping_address,
                    selected_routes=selected_routes,
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
                    segment_totals=segment_totals,
                )
            except Exception as tracking_exc:
                log_structured_event(
                    logger,
                    level="warning",
                    event="checkout_tracking_linkage_failed",
                    order_id=order.id,
                    error=str(tracking_exc),
                )

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
            user_id=current_user.id,
            amount=total_amount,
            currency=cart.currency,
            item_count=len(items),
            duration_ms=checkout_duration_ms,
        )

        return CheckoutResponse(
            order_id=order.id,
            payment_id=payment.id,
            cart_id=cart.id,
            subtotal_amount=subtotal_amount,
            shipping_fee_amount=shipping_fee_amount,
            payment_fee_amount=payment_fee_amount,
            total_fees_amount=total_fees_amount,
            total_amount=total_amount,
            currency=cart.currency,
            item_count=len(items),
            applied_shipping_route_ids=[route.id for route in selected_routes],
            shipping_eta_days=(
                shipping_cost_summary.eta_days if shipping_cost_summary else None
            ),
            shipping_carbon_footprint_kg_co2e=(
                shipping_cost_summary.carbon_footprint_kg_co2e
                if shipping_cost_summary
                else None
            ),
            shipping_cost_breakdown=shipping_cost_breakdown_payload,
            message="Checkout completed",
        )

    except HTTPException:
        checkout_duration_ms = int((perf_counter() - checkout_started) * 1000)
        observe_checkout_result(
            success=False,
            duration_ms=checkout_duration_ms,
            error_code="http_error",
        )
        log_structured_event(
            logger,
            level="warning",
            event="checkout_failed",
            user_id=current_user.id,
            error_code="http_error",
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
            user_id=current_user.id,
            error_code="internal_error",
            error=str(exc),
            duration_ms=checkout_duration_ms,
        )
        await session.rollback()
        raise HTTPException(status_code=500, detail="Checkout failed") from exc
