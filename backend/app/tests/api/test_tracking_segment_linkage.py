from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.cart import (
    FulfillmentAllocation,
    FulfillmentSegment,
    _link_fulfillment_segments_to_tracking,
    checkout_my_cart,
)
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import CheckoutRequest
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.payment.crud.payment import crud_payment
from app.features.user.models.user import User


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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_link_segments_creates_tracking_entries_with_consolidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id = uuid4()
    current_user = cast(User, SimpleNamespace(id=uuid4()))
    session = AsyncMock()

    address = SimpleNamespace(id=uuid4())
    pending_route_tracking_status = SimpleNamespace(id=uuid4())
    pending_consolidation_status = SimpleNamespace(id=uuid4())

    local_route = SimpleNamespace(id=uuid4())
    consolidation_route = SimpleNamespace(id=uuid4())

    create_tracking_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    create_consolidation_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))

    async def resolve_route_for_segment(
        session: object,
        *,
        segment: FulfillmentSegment,
        origin_place_id: object = None,
    ) -> object:
        _ = (session, origin_place_id)
        if segment == FulfillmentSegment.LOCAL:
            return local_route
        return consolidation_route

    monkeypatch.setattr(
        "app.api.routes.cart._resolve_tracking_address_for_checkout",
        AsyncMock(return_value=address),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_tracking_status",
        AsyncMock(
            side_effect=[
                pending_route_tracking_status,
                pending_consolidation_status,
            ]
        ),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._resolve_tracking_route_for_segment",
        AsyncMock(side_effect=resolve_route_for_segment),
    )
    monkeypatch.setattr(
        "app.api.routes.cart.crud_shipping_route_tracking.create_draft",
        create_tracking_mock,
    )
    monkeypatch.setattr(
        "app.api.routes.cart.crud_shipping_route_tracking_consolidation.create_draft",
        create_consolidation_mock,
    )

    await _link_fulfillment_segments_to_tracking(
        session=session,
        order_id=order_id,
        current_user=current_user,
        shipping_address="Papeete, PF",
        segment_totals={
            (FulfillmentSegment.LOCAL, None): Decimal("1.00"),
            (FulfillmentSegment.CONSOLIDATION_PF, None): Decimal("2.00"),
        },
    )

    assert create_tracking_mock.await_count == 2
    assert create_consolidation_mock.await_count == 1

    local_tracking_data = create_tracking_mock.await_args_list[0].kwargs["data"]
    consolidation_tracking_data = create_tracking_mock.await_args_list[1].kwargs["data"]

    assert local_tracking_data.order_id == order_id
    assert local_tracking_data.route_id == local_route.id
    assert local_tracking_data.status_id == pending_route_tracking_status.id
    assert local_tracking_data.address_id == address.id
    assert local_tracking_data.sequence_order == 1
    assert local_tracking_data.consolidation_id is None

    assert consolidation_tracking_data.route_id == consolidation_route.id
    assert consolidation_tracking_data.sequence_order == 2
    assert consolidation_tracking_data.consolidation_id is not None


@pytest.mark.anyio
async def test_checkout_calls_tracking_linker_with_segment_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    cart_id = uuid4()
    order_id = uuid4()
    payment_id = uuid4()
    product_id = uuid4()

    current_user = cast(User, SimpleNamespace(id=user_id))
    session = AsyncMock()
    session.add = Mock()

    cart = SimpleNamespace(
        id=cart_id,
        user_id=user_id,
        currency="XPF",
        total_amount=Decimal("0.00"),
        is_checked_out=False,
    )
    item = SimpleNamespace(
        id=uuid4(),
        cart_id=cart_id,
        product_id=product_id,
        quantity=3,
        unit_price=Decimal("10.00"),
        is_active=True,
    )
    product = SimpleNamespace(
        id=product_id,
        base_price=Decimal("10.00"),
        is_active=True,
        is_admin_active=True,
        is_supplier_managed=True,
        supplier_quantity=Decimal("10.00"),
    )

    order_status = SimpleNamespace(id=uuid4())
    payment_status = SimpleNamespace(id=uuid4())
    order = SimpleNamespace(id=order_id, total_amount=Decimal("0.00"))
    payment = SimpleNamespace(id=payment_id, payment_status_id=None)

    reserve_mock = AsyncMock(
        return_value=[
            FulfillmentAllocation(
                segment=FulfillmentSegment.LOCAL,
                quantity=Decimal("1.00"),
            ),
            FulfillmentAllocation(
                segment=FulfillmentSegment.SUPPLIER_DIRECT,
                quantity=Decimal("2.00"),
            ),
        ]
    )
    tracking_linker_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=cart),
    )
    monkeypatch.setattr(
        crud_cart_item,
        "get_by_cart_id",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_order_pending_status",
        AsyncMock(return_value=order_status),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404",
        AsyncMock(return_value=product),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._reserve_stock_for_checkout",
        reserve_mock,
    )
    monkeypatch.setattr(
        crud_order,
        "create_draft",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(
        crud_order_line,
        "create_draft",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._link_fulfillment_segments_to_tracking",
        tracking_linker_mock,
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_payment_pending_status",
        AsyncMock(return_value=payment_status),
    )
    monkeypatch.setattr(
        crud_payment,
        "create_draft",
        AsyncMock(return_value=payment),
    )
    # resolve_default_price_group queries through the raw session, which an
    # AsyncMock cannot serve (result.first() would be a stray coroutine).
    monkeypatch.setattr(
        "app.api.routes.cart.resolve_default_price_group",
        AsyncMock(return_value=None),
    )

    await checkout_my_cart(
        session=session,
        current_user=current_user,
        payload=CheckoutRequest(shipping_address="Paris, France"),
    )

    assert tracking_linker_mock.await_args is not None
    kwargs = tracking_linker_mock.await_args.kwargs

    assert kwargs["order_id"] == order_id
    assert kwargs["shipping_address"] == "Paris, France"
    assert kwargs["segment_totals"] == {
        (FulfillmentSegment.LOCAL, None): Decimal("1.00"),
        (FulfillmentSegment.SUPPLIER_DIRECT, None): Decimal("2.00"),
    }
