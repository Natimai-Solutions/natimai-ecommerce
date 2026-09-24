"""Pre-order modes at checkout (spec B1): ``on_demand`` and ``continuous``
products are accepted beyond the known stock and never reserve supplier
stock; ``stock`` products keep the historical guard."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.cart import (
    FulfillmentAllocation,
    FulfillmentSegment,
    _plan_checkout_fulfillment_segments,
    _reserve_stock_for_checkout,
)
from app.core.errors import AppError
from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.product.models.product import AvailabilityMode, Product
from app.features.user.models.user import User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _product(mode: AvailabilityMode | None, supplier_quantity: str) -> Product:
    fields: dict[str, object] = {
        "id": uuid4(),
        "base_price": Decimal("9.99"),
        "is_supplier_managed": True,
        "supplier_quantity": Decimal(supplier_quantity),
    }
    if mode is not None:
        fields["availability_mode"] = mode
    return cast(Product, SimpleNamespace(**fields))


def test_plan_segments_backorder_takes_the_uncovered_quantity_from_the_supplier() -> (
    None
):
    product = _product(AvailabilityMode.ON_DEMAND, "0")

    with pytest.raises(AppError) as guarded:
        _plan_checkout_fulfillment_segments(
            product=product,
            quantity=5,
            local_available=Decimal("1"),
            supplier_available=Decimal("2"),
        )
    assert guarded.value.code == "cart.stock.insufficient"

    segments = _plan_checkout_fulfillment_segments(
        product=product,
        quantity=5,
        local_available=Decimal("1"),
        supplier_available=Decimal("2"),
        backorder=True,
    )
    assert [(s.segment, s.quantity) for s in segments] == [
        (FulfillmentSegment.LOCAL, Decimal("1")),
        (FulfillmentSegment.VIA_MAIN_WAREHOUSE, Decimal("4")),
    ]


async def _reserve(
    monkeypatch: pytest.MonkeyPatch, product: Product, quantity: int
) -> tuple[list[FulfillmentAllocation], AsyncMock]:
    session = AsyncMock()
    session.add = Mock()
    movement_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        crud_inventory, "get_by_product_and_place", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(crud_stock_movement, "create_draft", movement_mock)
    segments = await _reserve_stock_for_checkout(
        session=session,
        order_id=uuid4(),
        product=product,
        quantity=quantity,
        current_user=cast(User, SimpleNamespace(id=uuid4())),
    )
    return segments, movement_mock


@pytest.mark.anyio
async def test_on_demand_is_accepted_beyond_stock_without_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = _product(AvailabilityMode.ON_DEMAND, "2")

    segments, movements = await _reserve(monkeypatch, product, quantity=5)

    assert [(s.segment, s.quantity) for s in segments] == [
        (FulfillmentSegment.VIA_MAIN_WAREHOUSE, Decimal("5"))
    ]
    # Nothing reserved: the supplier quantity is untouched and no movement
    # exists for the stock-release sweep to credit back.
    assert product.supplier_quantity == Decimal("2")
    movements.assert_not_awaited()


@pytest.mark.anyio
async def test_on_demand_needs_supplier_stock_at_the_last_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(AppError) as refused:
        await _reserve(monkeypatch, _product(AvailabilityMode.ON_DEMAND, "0"), 1)
    assert refused.value.code == "cart.stock.unavailable"


@pytest.mark.anyio
async def test_continuous_is_orderable_with_no_stock_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = _product(AvailabilityMode.CONTINUOUS, "0")

    segments, movements = await _reserve(monkeypatch, product, quantity=3)

    assert segments[0].quantity == Decimal("3")
    assert product.supplier_quantity == Decimal("0")
    movements.assert_not_awaited()


@pytest.mark.anyio
async def test_stock_mode_keeps_the_historical_guard_and_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A bare product (no availability_mode) behaves as 'stock'.
    with pytest.raises(AppError) as refused:
        await _reserve(monkeypatch, _product(None, "2"), 5)
    assert refused.value.code == "cart.stock.insufficient"

    product = _product(AvailabilityMode.STOCK, "4")
    segments, movements = await _reserve(monkeypatch, product, quantity=3)
    assert segments[0].quantity == Decimal("3")
    assert product.supplier_quantity == Decimal("1")
    movements.assert_awaited_once()
