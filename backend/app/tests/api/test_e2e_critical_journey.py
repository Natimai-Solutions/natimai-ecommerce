from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_superuser
from app.api.routes.cart import FulfillmentAllocation, FulfillmentSegment
from app.core.db import get_db
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import Cart, CartItem
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.order.models.order import Order, OrderCreate
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import Payment, PaymentCreate
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product
from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_shipping_route_tracking_consolidation,
    crud_status_definition,
)
from app.features.shipping.models.route_tracking import ShippingRouteTracking
from app.features.shipping.models.status import StatusDefinition
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import crud_user
from app.features.user.models.user import User
from app.main import app


@pytest.fixture(autouse=True)
def _stub_order_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checkout draws its order number from a PostgreSQL sequence (M5).

    These tests run on a mocked session, so the allocation is stubbed here;
    the numbering itself is covered by test_invoice_numbering_and_pdf.py and
    the integration suite.
    """
    monkeypatch.setattr(
        "app.api.routes.cart.allocate_order_number",
        AsyncMock(return_value="CMD-2026-00001"),
    )


@dataclass(frozen=True)
class StatusRef:
    id: uuid.UUID


@dataclass
class E1State:
    user: User
    product: Product
    cart: Cart
    cart_items: list[CartItem]
    orders: dict[uuid.UUID, Order]
    payments: dict[uuid.UUID, Payment]
    trackings_by_order: dict[uuid.UUID, list[ShippingRouteTracking]]
    tracking_logs: dict[uuid.UUID, list[Any]]
    order_status: StatusRef
    payment_status: StatusRef
    tracking_status: StatusDefinition
    route_id: uuid.UUID
    address_id: uuid.UUID
    session: InMemorySession | None = None


class _EmptyExecResult:
    def first(self) -> None:
        return None

    def all(self) -> list[Any]:
        return []


class InMemorySession:
    def __init__(self, state: E1State) -> None:
        self._state = state

    async def get(self, model: type[Any], record_id: Any) -> Any:
        if model is User and str(record_id) == str(self._state.user.id):
            return self._state.user
        return None

    async def exec(self, _statement: Any) -> _EmptyExecResult:
        # Pricing/tax helpers (resolve_default_price_group, resolve_tax_rate)
        # issue session.exec() directly during checkout. The journey assertions
        # don't depend on their results, so an empty result is sufficient:
        # price_group and tax_rate gracefully default to None.
        return _EmptyExecResult()

    def add(self, _record: Any) -> None:
        return

    async def flush(self) -> None:
        # outbox_registry.publish() flushes to obtain the event id; the journey
        # does not inspect outbox rows, so a no-op is sufficient.
        return

    async def commit(self) -> None:
        return

    async def refresh(self, _record: Any) -> None:
        return

    async def rollback(self) -> None:
        return


@pytest.fixture
def e1_state() -> E1State:
    user = User(
        id=uuid.uuid4(),
        email="e1-user@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    product = Product(
        id=uuid.uuid4(),
        name="E1 Test Product",
        description="Produit de test E1",
        base_price=Decimal("10.00"),
        is_active=True,
        is_admin_active=True,
        is_supplier_managed=True,
        supplier_quantity=Decimal("50.00"),
    )
    cart = Cart(
        id=uuid.uuid4(),
        user_id=user.id,
        currency="XPF",
        total_amount=Decimal("0.00"),
        is_checked_out=False,
    )
    tracking_status = StatusDefinition(
        id=uuid.uuid4(),
        entity="route_tracking",
        code="pending",
        name="Pending",
        description=None,
        sequence_order=0,
        is_terminal=False,
        is_error=False,
        ui_color=None,
        ui_icon=None,
    )

    state = E1State(
        user=user,
        product=product,
        cart=cart,
        cart_items=[],
        orders={},
        payments={},
        trackings_by_order={},
        tracking_logs={},
        order_status=StatusRef(id=uuid.uuid4()),
        payment_status=StatusRef(id=uuid.uuid4()),
        tracking_status=tracking_status,
        route_id=uuid.uuid4(),
        address_id=uuid.uuid4(),
    )
    state.session = InMemorySession(state)
    return state


@pytest.fixture(autouse=True)
def override_db_dependency(e1_state: E1State) -> Generator[None, None, None]:
    async def _override_get_db() -> AsyncGenerator[InMemorySession, None]:
        if e1_state.session is None:
            raise RuntimeError("Missing in-memory session")
        yield e1_state.session

    async def _override_superuser() -> SimpleNamespace:
        return SimpleNamespace(id=e1_state.user.id, is_superuser=True, is_active=True)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_active_superuser] = _override_superuser
    yield
    app.dependency_overrides.clear()


def test_e1_critical_journey_login_catalog_cart_checkout_payment_tracking_history(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    e1_state: E1State,
) -> None:
    async def _product_read_multi(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "data": [e1_state.product],
            "count": 1,
        }

    async def _cart_get_or_create(*_args: Any, **_kwargs: Any) -> Cart:
        return e1_state.cart

    async def _cart_add_or_increment(
        *_args: Any,
        cart_id: uuid.UUID,
        product: Product,
        quantity: int,
        **_kwargs: Any,
    ) -> CartItem:
        for item in e1_state.cart_items:
            if (
                item.cart_id == cart_id
                and item.product_id == product.id
                and item.is_active
            ):
                item.quantity += quantity
                return item

        cart_item = CartItem(
            id=uuid.uuid4(),
            cart_id=cart_id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.base_price,
            is_active=True,
        )
        e1_state.cart_items.append(cart_item)
        return cart_item

    async def _cart_sync_total(*_args: Any, **_kwargs: Any) -> Decimal:
        total = sum(
            (
                item.unit_price * item.quantity
                for item in e1_state.cart_items
                if item.is_active
            ),
            Decimal("0.00"),
        )
        e1_state.cart.total_amount = total
        return total

    async def _cart_get_items(
        *_args: Any,
        cart_id: uuid.UUID,
        **_kwargs: Any,
    ) -> list[CartItem]:
        return [
            item
            for item in e1_state.cart_items
            if item.cart_id == cart_id and item.is_active
        ]

    async def _cart_get_active(*_args: Any, **_kwargs: Any) -> Cart:
        return e1_state.cart

    async def _create_order(*_args: Any, data: OrderCreate, **_kwargs: Any) -> Order:
        order = Order(
            id=uuid.uuid4(),
            user_id=data.user_id,
            order_status_id=data.order_status_id,
            total_amount=data.total_amount,
            subtotal_amount=data.subtotal_amount,
            shipping_fee_amount=data.shipping_fee_amount,
            payment_fee_amount=data.payment_fee_amount,
            total_fees_amount=data.total_fees_amount,
            shipping_address=data.shipping_address,
            notes=data.notes,
            is_active=True,
        )
        e1_state.orders[order.id] = order
        return order

    async def _create_payment(
        *_args: Any,
        data: PaymentCreate,
        **_kwargs: Any,
    ) -> Payment:
        payment = Payment(
            id=uuid.uuid4(),
            amount=data.amount,
            currency=data.currency,
            order_id=data.order_id,
            user_id=data.user_id,
            payment_status_id=None,
            is_active=True,
        )
        e1_state.payments[payment.id] = payment
        return payment

    async def _reserve_for_checkout(
        *_args: Any,
        quantity: int,
        **_kwargs: Any,
    ) -> list[FulfillmentAllocation]:
        return [
            FulfillmentAllocation(
                segment=FulfillmentSegment.LOCAL,
                quantity=Decimal(quantity),
            )
        ]

    async def _link_segments(
        *_args: Any,
        order_id: uuid.UUID,
        segment_totals: dict[tuple[FulfillmentSegment, uuid.UUID | None], Decimal],
        **_kwargs: Any,
    ) -> None:
        trackings: list[ShippingRouteTracking] = []
        for sequence_order, ((segment, origin_place_id), quantity) in enumerate(
            segment_totals.items(),
            start=1,
        ):
            trackings.append(
                ShippingRouteTracking(
                    id=uuid.uuid4(),
                    order_id=order_id,
                    route_id=e1_state.route_id,
                    status_id=e1_state.tracking_status.id,
                    address_id=e1_state.address_id,
                    selected_at=datetime.now(timezone.utc),
                    sequence_order=sequence_order,
                    notes=(
                        f"segment={segment.value};quantity={quantity};"
                        f"origin={origin_place_id or 'e1_test'}"
                    ),
                    is_active=True,
                )
            )
        e1_state.trackings_by_order[order_id] = trackings

    async def _payment_read(*_args: Any, id: uuid.UUID, **_kwargs: Any) -> Payment:
        return e1_state.payments[id]

    async def _orders_by_user(
        *_args: Any,
        user_id: uuid.UUID,
        **_kwargs: Any,
    ) -> list[Order]:
        return [order for order in e1_state.orders.values() if order.user_id == user_id]

    async def _tracking_by_order(
        *_args: Any,
        order_id: uuid.UUID,
        **_kwargs: Any,
    ) -> ShippingRouteTracking | None:
        trackings = e1_state.trackings_by_order.get(order_id, [])
        if not trackings:
            return None
        return sorted(trackings, key=lambda tracking: tracking.sequence_order)[0]

    async def _trackings_by_order(
        *_args: Any,
        order_id: uuid.UUID,
        **_kwargs: Any,
    ) -> list[ShippingRouteTracking]:
        return sorted(
            e1_state.trackings_by_order.get(order_id, []),
            key=lambda tracking: tracking.sequence_order,
        )

    async def _tracking_read(
        *_args: Any,
        id: uuid.UUID,
        **_kwargs: Any,
    ) -> ShippingRouteTracking:
        for trackings in e1_state.trackings_by_order.values():
            for tracking in trackings:
                if tracking.id == id:
                    return tracking
        raise ValueError(f"tracking {id} not found")

    async def _tracking_logs(
        *_args: Any,
        tracking_id: uuid.UUID,
        **_kwargs: Any,
    ) -> list[Any]:
        return e1_state.tracking_logs.get(tracking_id, [])

    monkeypatch.setattr(
        crud_user,
        "authenticate",
        AsyncMock(return_value=e1_state.user),
    )
    monkeypatch.setattr(
        crud_user_refresh_token,
        "create_for_user",
        AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
    )
    monkeypatch.setattr(
        crud_product,
        "read_multi",
        AsyncMock(side_effect=_product_read_multi),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404",
        AsyncMock(return_value=e1_state.product),
    )
    monkeypatch.setattr(
        crud_cart,
        "get_or_create_active_cart",
        AsyncMock(side_effect=_cart_get_or_create),
    )
    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(side_effect=_cart_get_active),
    )
    monkeypatch.setattr(
        crud_cart,
        "sync_total",
        AsyncMock(side_effect=_cart_sync_total),
    )
    monkeypatch.setattr(
        crud_cart_item,
        "add_or_increment",
        AsyncMock(side_effect=_cart_add_or_increment),
    )
    monkeypatch.setattr(
        crud_cart_item,
        "get_by_cart_id",
        AsyncMock(side_effect=_cart_get_items),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_order_pending_status",
        AsyncMock(return_value=e1_state.order_status),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_payment_pending_status",
        AsyncMock(return_value=e1_state.payment_status),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._reserve_stock_for_checkout",
        AsyncMock(side_effect=_reserve_for_checkout),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._link_fulfillment_segments_to_tracking",
        AsyncMock(side_effect=_link_segments),
    )
    monkeypatch.setattr(
        crud_order,
        "create_draft",
        AsyncMock(side_effect=_create_order),
    )
    monkeypatch.setattr(
        crud_order_line,
        "create_draft",
        AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
    )
    monkeypatch.setattr(
        crud_order,
        "get_by_user",
        AsyncMock(side_effect=_orders_by_user),
    )
    monkeypatch.setattr(
        crud_payment,
        "create_draft",
        AsyncMock(side_effect=_create_payment),
    )
    monkeypatch.setattr(
        crud_payment,
        "read",
        AsyncMock(side_effect=_payment_read),
    )
    monkeypatch.setattr(
        crud_payment,
        "check_user_permission",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        crud_shipping_route_tracking,
        "get_by_order_id",
        AsyncMock(side_effect=_tracking_by_order),
    )
    monkeypatch.setattr(
        crud_shipping_route_tracking,
        "get_trackings_by_order_sequence",
        AsyncMock(side_effect=_trackings_by_order),
    )
    monkeypatch.setattr(
        crud_shipping_route_tracking,
        "read",
        AsyncMock(side_effect=_tracking_read),
    )
    monkeypatch.setattr(
        crud_shipping_route_tracking,
        "get_status_history",
        AsyncMock(side_effect=_tracking_logs),
    )
    monkeypatch.setattr(
        crud_shipping_route_tracking_consolidation,
        "get_consolidations_for_route",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        crud_status_definition,
        "get_by_entity",
        AsyncMock(return_value=[e1_state.tracking_status]),
    )

    login_response = client.post(
        "/api/v1/login/access-token",
        data={
            "username": e1_state.user.email,
            "password": "ignored-in-test",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    catalog_response = client.get("/api/v1/product/")
    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    assert catalog_payload["count"] == 1
    product_id = catalog_payload["data"][0]["id"]

    add_to_cart_response = client.post(
        "/api/v1/cart/items",
        headers=auth_headers,
        json={
            "product_id": product_id,
            "quantity": 2,
        },
    )
    assert add_to_cart_response.status_code == 201
    add_to_cart_payload = add_to_cart_response.json()
    assert len(add_to_cart_payload["items"]) == 1
    assert add_to_cart_payload["items"][0]["quantity"] == 2

    get_cart_response = client.get("/api/v1/cart/me", headers=auth_headers)
    assert get_cart_response.status_code == 200
    get_cart_payload = get_cart_response.json()
    assert len(get_cart_payload["items"]) == 1

    checkout_response = client.post(
        "/api/v1/cart/checkout",
        headers=auth_headers,
        json={
            "shipping_address": "Papeete, PF",
            "shipping_fee_amount": "1.00",
            "payment_fee_amount": "0.50",
            "cgv_accepted": True,
        },
    )
    assert checkout_response.status_code == 201
    checkout_payload = checkout_response.json()
    order_id = checkout_payload["order_id"]
    payment_id = checkout_payload["payment_id"]

    # The customer polls payment status via the ownership-scoped endpoint —
    # the raw /payment CRUD is superuser-only since the gating pass.
    payment_response = client.get(
        f"/api/v1/payments/me/{payment_id}",
        headers=auth_headers,
    )
    assert payment_response.status_code == 200
    payment_payload = payment_response.json()
    assert payment_payload["order_id"] == order_id

    tracking_response = client.get(
        f"/api/v1/shipping/tracking/order/{order_id}",
        headers=auth_headers,
    )
    assert tracking_response.status_code == 200
    tracking_payload = tracking_response.json()
    assert tracking_payload["overall_status"] == "pending"
    assert tracking_payload["exception_scenarios"] == []
    assert tracking_payload["current_route_sequence"] == 1
    assert len(tracking_payload["trackings"]) == 1
    tracking_id = tracking_payload["trackings"][0]["id"]

    tracking_history_response = client.get(
        f"/api/v1/shipping/tracking/{tracking_id}/history",
        headers=auth_headers,
    )
    assert tracking_history_response.status_code == 200
    assert tracking_history_response.json()["total_changes"] == 0

    order_history_response = client.get(
        f"/api/v1/order/user/{e1_state.user.id}",
        headers=auth_headers,
    )
    assert order_history_response.status_code == 200
    order_history_payload = order_history_response.json()
    assert len(order_history_payload) == 1
    assert order_history_payload[0]["id"] == order_id
