from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.cart import (
    FulfillmentAllocation,
    FulfillmentSegment,
    _format_fulfillment_segments_note,
    _plan_checkout_fulfillment_segments,
    _reserve_stock_for_checkout,
    checkout_my_cart,
)
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import CheckoutRequest
from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.payment.crud.payment import crud_payment
from app.features.product.models.product import Product
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


def test_plan_segments_uses_local_then_main_warehouse() -> None:
    product = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            is_supplier_managed=True,
        ),
    )

    segments = _plan_checkout_fulfillment_segments(
        product=product,
        quantity=4,
        local_available=Decimal("1.00"),
        supplier_available=Decimal("10.00"),
    )

    assert len(segments) == 2
    assert segments[0].segment == FulfillmentSegment.LOCAL
    assert segments[0].quantity == Decimal("1.00")
    assert segments[1].segment == FulfillmentSegment.VIA_MAIN_WAREHOUSE
    assert segments[1].quantity == Decimal("3.00")


def test_plan_segments_uses_supplier_direct_when_dropship() -> None:
    product = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            is_supplier_managed=True,
        ),
    )

    segments = _plan_checkout_fulfillment_segments(
        product=product,
        quantity=2,
        local_available=Decimal("0.00"),
        supplier_available=Decimal("5.00"),
        supplier_segment=FulfillmentSegment.SUPPLIER_DIRECT,
    )

    assert len(segments) == 1
    assert segments[0].segment == FulfillmentSegment.SUPPLIER_DIRECT
    assert segments[0].quantity == Decimal("2.00")


@pytest.mark.anyio
async def test_reserve_stock_tags_supplier_movement_as_pf_consolidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=uuid4()))

    inventory = SimpleNamespace(quantity=Decimal("1.00"), place_id=uuid4())
    product = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            base_price=Decimal("9.99"),
            is_supplier_managed=True,
            supplier_quantity=Decimal("4.00"),
        ),
    )

    movement_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        crud_inventory,
        "get_by_product_and_place",
        AsyncMock(return_value=inventory),
    )
    monkeypatch.setattr(crud_stock_movement, "create_draft", movement_mock)

    segments = await _reserve_stock_for_checkout(
        session=session,
        order_id=uuid4(),
        product=product,
        quantity=3,
        current_user=current_user,
    )

    assert [segment.segment for segment in segments] == [
        FulfillmentSegment.LOCAL,
        FulfillmentSegment.VIA_MAIN_WAREHOUSE,
    ]

    supplier_movement = movement_mock.await_args_list[1].kwargs["data"]
    assert supplier_movement.reason.endswith("segment=consolidation_pf)")


@pytest.mark.anyio
async def test_checkout_persists_segment_note_from_orchestration(
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
        quantity=2,
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
                segment=FulfillmentSegment.SUPPLIER_DIRECT,
                quantity=Decimal("2.00"),
            )
        ]
    )
    create_order_line_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))

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
        "app.api.routes.cart._link_fulfillment_segments_to_tracking",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        crud_order,
        "create_draft",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(crud_order_line, "create_draft", create_order_line_mock)
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
    # Same for the per-declaration customs fees (F3) — covered on their own in
    # test_checkout_customs_declaration_fee.py.
    monkeypatch.setattr(
        "app.api.routes.cart._customs_declaration_fees",
        AsyncMock(return_value=[]),
    )

    await checkout_my_cart(
        session=session,
        current_user=current_user,
        payload=CheckoutRequest(shipping_address="Paris, France", cgv_accepted=True),
    )

    assert reserve_mock.await_args is not None

    assert create_order_line_mock.await_args is not None
    line_create = create_order_line_mock.await_args.kwargs["data"]
    assert line_create.notes == "fulfillment_segments=supplier_direct:2"


def test_format_fulfillment_segments_note_is_stable() -> None:
    note = _format_fulfillment_segments_note(
        [
            FulfillmentAllocation(
                segment=FulfillmentSegment.LOCAL,
                quantity=Decimal("1.00"),
            ),
            FulfillmentAllocation(
                segment=FulfillmentSegment.VIA_MAIN_WAREHOUSE,
                quantity=Decimal("3.00"),
            ),
        ]
    )

    assert note == "fulfillment_segments=local:1,consolidation_pf:3"
