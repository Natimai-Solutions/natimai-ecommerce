from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.cart import (
    add_cart_item,
    clear_my_cart,
    get_my_cart,
    remove_cart_item,
    update_cart_item_quantity,
)
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import (
    CartItemAddRequest,
    CartItemQuantityUpdateRequest,
)
from app.features.user.models.user import User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_get_my_cart_returns_detail_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    cart_id = uuid4()
    product_id = uuid4()

    cart = SimpleNamespace(
        id=cart_id,
        user_id=user_id,
        currency="XPF",
        total_amount=Decimal("21.00"),
        is_checked_out=False,
    )
    item = SimpleNamespace(
        id=uuid4(),
        product_id=product_id,
        quantity=2,
        unit_price=Decimal("10.50"),
    )

    session = AsyncMock()
    current_user = cast(User, SimpleNamespace(id=user_id))

    get_or_create_mock = AsyncMock(return_value=cart)
    get_items_mock = AsyncMock(return_value=[item])

    monkeypatch.setattr(crud_cart, "get_or_create_active_cart", get_or_create_mock)
    monkeypatch.setattr(crud_cart_item, "get_by_cart_id", get_items_mock)

    result = await get_my_cart(session=session, current_user=current_user)

    assert result.id == cart_id
    assert result.total_amount == Decimal("21.00")
    assert len(result.items) == 1
    assert result.items[0].product_id == product_id
    assert result.items[0].line_total == Decimal("21")


@pytest.mark.anyio
async def test_add_cart_item_increments_and_recomputes_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    cart_id = uuid4()
    product_id = uuid4()

    cart = SimpleNamespace(
        id=cart_id,
        user_id=user_id,
        currency="EUR",
        total_amount=Decimal("31.50"),
        is_checked_out=False,
    )
    product = SimpleNamespace(id=product_id, base_price=Decimal("10.50"))
    item = SimpleNamespace(
        id=uuid4(),
        product_id=product_id,
        quantity=3,
        unit_price=Decimal("10.50"),
    )

    session = AsyncMock()
    current_user = cast(User, SimpleNamespace(id=user_id))

    get_or_create_mock = AsyncMock(return_value=cart)
    add_mock = AsyncMock(return_value=item)
    sync_total_mock = AsyncMock(return_value=Decimal("31.50"))
    get_items_mock = AsyncMock(return_value=[item])
    get_product_mock = AsyncMock(return_value=product)

    monkeypatch.setattr(crud_cart, "get_or_create_active_cart", get_or_create_mock)
    monkeypatch.setattr(crud_cart_item, "add_or_increment", add_mock)
    monkeypatch.setattr(crud_cart, "sync_total", sync_total_mock)
    monkeypatch.setattr(crud_cart_item, "get_by_cart_id", get_items_mock)
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404", get_product_mock
    )

    result = await add_cart_item(
        session=session,
        current_user=current_user,
        payload=CartItemAddRequest(product_id=product_id, quantity=1),
    )

    add_mock.assert_awaited_once()
    sync_total_mock.assert_awaited_once_with(session=session, cart_id=cart_id)
    assert result.id == cart_id
    assert result.total_amount == Decimal("31.50")
    assert result.items[0].quantity == 3


@pytest.mark.anyio
async def test_update_cart_item_quantity_returns_404_when_item_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    current_user = cast(User, SimpleNamespace(id=uuid4()))

    get_item_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(crud_cart_item, "get_active_item_for_user", get_item_mock)

    with pytest.raises(HTTPException) as exc_info:
        await update_cart_item_quantity(
            session=session,
            current_user=current_user,
            item_id=uuid4(),
            payload=CartItemQuantityUpdateRequest(quantity=2),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Cart item not found"


@pytest.mark.anyio
async def test_remove_and_clear_cart_keep_total_at_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    cart_id = uuid4()

    session = AsyncMock()
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
        product_id=uuid4(),
        quantity=1,
        unit_price=Decimal("5"),
    )

    get_item_mock = AsyncMock(return_value=item)
    deactivate_mock = AsyncMock(return_value=None)
    sync_total_mock = AsyncMock(return_value=Decimal("0.00"))
    get_items_mock = AsyncMock(return_value=[])
    clear_mock = AsyncMock(return_value=1)
    get_or_create_mock = AsyncMock(return_value=cart)

    monkeypatch.setattr(crud_cart_item, "get_active_item_for_user", get_item_mock)
    monkeypatch.setattr(crud_cart_item, "deactivate_item", deactivate_mock)
    monkeypatch.setattr(crud_cart, "sync_total", sync_total_mock)
    monkeypatch.setattr(crud_cart_item, "get_by_cart_id", get_items_mock)
    monkeypatch.setattr(crud_cart_item, "clear_cart", clear_mock)
    monkeypatch.setattr(crud_cart, "get_or_create_active_cart", get_or_create_mock)

    session.get = AsyncMock(return_value=cart)

    removed = await remove_cart_item(
        session=session,
        current_user=current_user,
        item_id=item.id,
    )
    assert removed.total_amount == Decimal("0.00")
    assert removed.items == []

    cleared = await clear_my_cart(
        session=session,
        current_user=current_user,
    )
    assert cleared.total_amount == Decimal("0.00")
    assert cleared.items == []
