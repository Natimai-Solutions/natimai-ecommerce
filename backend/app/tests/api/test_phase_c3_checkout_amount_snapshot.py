from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.cart import _snapshot_checkout_amounts, checkout_my_cart
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import CartItem, CheckoutRequest
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.payment.crud.payment import crud_payment
from app.features.user.models.user import User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_snapshot_checkout_amounts_quantizes_with_currency_rules() -> None:
    items = cast(
        list[CartItem],
        [
            SimpleNamespace(unit_price=Decimal("10.50"), quantity=2),
        ],
    )

    (
        subtotal_amount,
        shipping_fee_amount,
        payment_fee_amount,
        total_fees_amount,
        total_amount,
    ) = _snapshot_checkout_amounts(
        items=items,
        currency="XPF",
        shipping_fee_amount=Decimal("1.50"),
        payment_fee_amount=Decimal("0.49"),
    )

    assert subtotal_amount == Decimal("21")
    assert shipping_fee_amount == Decimal("2")
    assert payment_fee_amount == Decimal("0")
    assert total_fees_amount == Decimal("2")
    assert total_amount == Decimal("23")


@pytest.mark.anyio
async def test_checkout_freezes_subtotal_and_fees_into_order_and_payment(
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
        currency="EUR",
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
        is_supplier_managed=False,
        supplier_quantity=Decimal("0.00"),
    )

    order_status = SimpleNamespace(id=uuid4())
    payment_status = SimpleNamespace(id=uuid4())
    order = SimpleNamespace(id=order_id, total_amount=Decimal("0.00"))
    payment = SimpleNamespace(id=payment_id, payment_status_id=None)

    get_active_cart_mock = AsyncMock(return_value=cart)
    get_items_mock = AsyncMock(return_value=[item])
    create_order_mock = AsyncMock(return_value=order)
    create_order_line_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    create_payment_mock = AsyncMock(return_value=payment)

    monkeypatch.setattr(crud_cart, "get_active_cart_by_user", get_active_cart_mock)
    monkeypatch.setattr(crud_cart_item, "get_by_cart_id", get_items_mock)
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
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(crud_order, "create_draft", create_order_mock)
    monkeypatch.setattr(crud_order_line, "create_draft", create_order_line_mock)
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_payment_pending_status",
        AsyncMock(return_value=payment_status),
    )
    monkeypatch.setattr(crud_payment, "create_draft", create_payment_mock)

    response = await checkout_my_cart(
        session=session,
        current_user=current_user,
        payload=CheckoutRequest(
            shipping_fee_amount=Decimal("2.50"),
            payment_fee_amount=Decimal("1.25"),
        ),
    )

    assert create_order_mock.await_args is not None
    assert create_payment_mock.await_args is not None

    order_create = create_order_mock.await_args.kwargs["data"]
    payment_create = create_payment_mock.await_args.kwargs["data"]

    assert order_create.subtotal_amount == Decimal("20.00")
    assert order_create.shipping_fee_amount == Decimal("2.50")
    assert order_create.payment_fee_amount == Decimal("1.25")
    assert order_create.total_fees_amount == Decimal("3.75")
    assert order_create.total_amount == Decimal("23.75")

    assert payment_create.amount == Decimal("23.75")
    assert payment_create.currency == "EUR"

    assert response.subtotal_amount == Decimal("20.00")
    assert response.shipping_fee_amount == Decimal("2.50")
    assert response.payment_fee_amount == Decimal("1.25")
    assert response.total_fees_amount == Decimal("3.75")
    assert response.total_amount == Decimal("23.75")
