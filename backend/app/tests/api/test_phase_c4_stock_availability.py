from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.cart import _reserve_stock_for_checkout
from app.core.errors import AppError
from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.product.models.product import Product
from app.features.user.models.user import User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_reserve_stock_uses_local_inventory_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=uuid4()))
    order_id = uuid4()

    inventory = SimpleNamespace(quantity=Decimal("5.00"), place_id=None)
    product = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            base_price=Decimal("10.00"),
            is_supplier_managed=False,
            supplier_quantity=Decimal("0.00"),
        ),
    )

    movement_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        crud_inventory,
        "get_by_product_and_place",
        AsyncMock(return_value=inventory),
    )
    monkeypatch.setattr(crud_stock_movement, "create_draft", movement_mock)

    await _reserve_stock_for_checkout(
        session=session,
        order_id=order_id,
        product=product,
        quantity=3,
        current_user=current_user,
    )

    assert inventory.quantity == Decimal("2.00")
    assert product.supplier_quantity == Decimal("0.00")
    assert movement_mock.await_count == 1
    local_movement = movement_mock.await_args_list[0].kwargs["data"]
    assert local_movement.quantity == Decimal("3")


@pytest.mark.anyio
async def test_reserve_stock_falls_back_to_supplier_when_local_is_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=uuid4()))
    order_id = uuid4()

    inventory = SimpleNamespace(quantity=Decimal("1.00"), place_id=uuid4())
    product = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            base_price=Decimal("9.50"),
            is_supplier_managed=True,
            supplier_quantity=Decimal("10.00"),
        ),
    )

    movement_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        crud_inventory,
        "get_by_product_and_place",
        AsyncMock(return_value=inventory),
    )
    monkeypatch.setattr(crud_stock_movement, "create_draft", movement_mock)

    await _reserve_stock_for_checkout(
        session=session,
        order_id=order_id,
        product=product,
        quantity=4,
        current_user=current_user,
    )

    assert inventory.quantity == Decimal("0.00")
    assert product.supplier_quantity == Decimal("7.00")
    assert movement_mock.await_count == 2

    local_movement = movement_mock.await_args_list[0].kwargs["data"]
    supplier_movement = movement_mock.await_args_list[1].kwargs["data"]

    assert local_movement.quantity == Decimal("1")
    assert supplier_movement.quantity == Decimal("3")


@pytest.mark.anyio
async def test_reserve_stock_uses_supplier_only_when_no_local_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=uuid4()))
    order_id = uuid4()

    product = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            base_price=Decimal("12.00"),
            is_supplier_managed=True,
            supplier_quantity=Decimal("4.00"),
        ),
    )

    movement_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        crud_inventory,
        "get_by_product_and_place",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(crud_stock_movement, "create_draft", movement_mock)

    await _reserve_stock_for_checkout(
        session=session,
        order_id=order_id,
        product=product,
        quantity=2,
        current_user=current_user,
    )

    assert product.supplier_quantity == Decimal("2.00")
    assert movement_mock.await_count == 1
    supplier_movement = movement_mock.await_args_list[0].kwargs["data"]
    assert supplier_movement.quantity == Decimal("2")


@pytest.mark.anyio
async def test_reserve_stock_raises_when_local_and_supplier_are_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=uuid4()))

    inventory = SimpleNamespace(quantity=Decimal("1.00"), place_id=None)
    product = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            base_price=Decimal("8.00"),
            is_supplier_managed=True,
            supplier_quantity=Decimal("1.00"),
        ),
    )

    movement_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        crud_inventory,
        "get_by_product_and_place",
        AsyncMock(return_value=inventory),
    )
    monkeypatch.setattr(crud_stock_movement, "create_draft", movement_mock)

    with pytest.raises(AppError) as exc_info:
        await _reserve_stock_for_checkout(
            session=session,
            order_id=uuid4(),
            product=product,
            quantity=4,
            current_user=current_user,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "cart.stock.insufficient"
    assert exc_info.value.details["product_id"] == str(product.id)
    movement_mock.assert_not_awaited()
