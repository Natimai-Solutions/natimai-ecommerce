from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.cart import checkout_my_cart
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import CheckoutRequest
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.payment.crud.payment import crud_payment
from app.features.user.models.user import User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_checkout_creates_order_payment_and_marks_cart_checked_out(
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
        is_supplier_managed=False,
        supplier_quantity=Decimal("0.00"),
    )

    order_status = SimpleNamespace(id=uuid4())
    payment_status = SimpleNamespace(id=uuid4())
    order = SimpleNamespace(id=order_id, total_amount=Decimal("0.00"))
    payment = SimpleNamespace(id=payment_id, payment_status_id=None)

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
        AsyncMock(return_value=None),
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
        "app.api.routes.cart._get_or_create_payment_pending_status",
        AsyncMock(return_value=payment_status),
    )
    monkeypatch.setattr(
        crud_payment,
        "create_draft",
        AsyncMock(return_value=payment),
    )

    response = await checkout_my_cart(
        session=session,
        current_user=current_user,
        payload=CheckoutRequest(shipping_address="Papeete", notes="RAS"),
    )

    assert response.order_id == order_id
    assert response.payment_id == payment_id
    assert response.cart_id == cart_id
    assert response.item_count == 1
    assert response.total_amount == Decimal("20")

    assert payment.payment_status_id == payment_status.id
    assert order.total_amount == Decimal("20")
    assert cart.is_checked_out is True
    assert item.is_active is False

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_checkout_rejects_missing_active_cart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=uuid4()))

    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        await checkout_my_cart(
            session=session,
            current_user=current_user,
            payload=CheckoutRequest(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No active cart found"


@pytest.mark.anyio
async def test_checkout_rejects_empty_cart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=user_id))
    cart = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        currency="XPF",
        total_amount=Decimal("0.00"),
        is_checked_out=False,
    )

    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=cart),
    )
    monkeypatch.setattr(
        crud_cart_item,
        "get_by_cart_id",
        AsyncMock(return_value=[]),
    )

    with pytest.raises(HTTPException) as exc_info:
        await checkout_my_cart(
            session=session,
            current_user=current_user,
            payload=CheckoutRequest(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cart is empty"


@pytest.mark.anyio
async def test_checkout_rolls_back_when_stock_reservation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    cart_id = uuid4()
    product_id = uuid4()

    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=user_id))

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
        quantity=1,
        unit_price=Decimal("9.99"),
        is_active=True,
    )
    product = SimpleNamespace(
        id=product_id,
        base_price=Decimal("9.99"),
        is_active=True,
        is_admin_active=True,
        is_supplier_managed=False,
        supplier_quantity=Decimal("0.00"),
    )

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
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        crud_order,
        "create_draft",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), total_amount=Decimal("0.00"))),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404",
        AsyncMock(return_value=product),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._reserve_stock_for_checkout",
        AsyncMock(side_effect=HTTPException(status_code=409, detail="Insufficient stock")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await checkout_my_cart(
            session=session,
            current_user=current_user,
            payload=CheckoutRequest(),
        )

    assert exc_info.value.status_code == 409
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
