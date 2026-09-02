"""The checkout total is decided by the server, not by the caller.

Two holes this covers:

* ``CartItem.unit_price`` is snapshotted when the line is added, and the
  checkout used to bill that snapshot while discarding the price it had just
  recomputed. A supplier sync runs every two hours, so the displayed price and
  the billed price could differ with nobody noticing.
* ``payment_fee_amount`` arrived in the request body and was taken at face
  value, letting the caller decide what its own payment method costs.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.api.routes.cart import _resolve_payment_fee, _revalidate_checkout_prices
from app.core.errors import AppError
from app.features.cart.models.cart import CartItem
from app.features.product.models.product import Product


def _item(product_id: UUID, *, unit_price: str, quantity: int = 2) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        product_id=product_id,
        quantity=quantity,
        unit_price=Decimal(unit_price),
    )


def _product(product_id: UUID, *, base_price: str, name: str = "Écran 27") -> Any:
    return SimpleNamespace(id=product_id, name=name, base_price=Decimal(base_price))


# -- price revalidation -----------------------------------------------------


@pytest.mark.asyncio
async def test_unchanged_prices_let_the_checkout_through() -> None:
    product_id = uuid4()
    session = AsyncMock()
    session.add = Mock()

    await _revalidate_checkout_prices(
        session,
        items=cast(list[CartItem], [_item(product_id, unit_price="10.00")]),
        products_by_id=cast(
            dict[UUID, Product], {product_id: _product(product_id, base_price="10.00")}
        ),
        currency="EUR",
    )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_price_increase_stops_the_checkout() -> None:
    """Billing more than the displayed price is not what the customer agreed to."""
    product_id = uuid4()
    session = AsyncMock()
    session.add = Mock()
    item = _item(product_id, unit_price="10.00")

    with pytest.raises(AppError) as excinfo:
        await _revalidate_checkout_prices(
            session,
            items=cast(list[CartItem], [item]),
            products_by_id=cast(
                dict[UUID, Product],
                {product_id: _product(product_id, base_price="12.50")},
            ),
            currency="EUR",
        )

    error = excinfo.value
    assert error.code == "cart.price.changed"
    assert error.status_code == 409
    drifted = error.details["items"]
    assert drifted[0]["previous_unit_price"] == "10.00"
    assert drifted[0]["current_unit_price"] == "12.50"


@pytest.mark.asyncio
async def test_a_price_drop_also_stops_the_checkout() -> None:
    """Charging the old, higher price would be just as wrong."""
    product_id = uuid4()
    session = AsyncMock()
    session.add = Mock()

    with pytest.raises(AppError) as excinfo:
        await _revalidate_checkout_prices(
            session,
            items=cast(list[CartItem], [_item(product_id, unit_price="10.00")]),
            products_by_id=cast(
                dict[UUID, Product],
                {product_id: _product(product_id, base_price="8.00")},
            ),
            currency="EUR",
        )

    assert excinfo.value.code == "cart.price.changed"


@pytest.mark.asyncio
async def test_the_cart_is_refreshed_before_the_error_is_raised() -> None:
    """The client re-reads the cart on this error and must see the new price."""
    product_id = uuid4()
    session = AsyncMock()
    session.add = Mock()
    item = _item(product_id, unit_price="10.00")

    with pytest.raises(AppError):
        await _revalidate_checkout_prices(
            session,
            items=cast(list[CartItem], [item]),
            products_by_id=cast(
                dict[UUID, Product],
                {product_id: _product(product_id, base_price="12.50")},
            ),
            currency="EUR",
        )

    assert item.unit_price == Decimal("12.50")
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_every_drifted_line_is_reported_not_just_the_first() -> None:
    first, second, stable = uuid4(), uuid4(), uuid4()
    session = AsyncMock()
    session.add = Mock()

    with pytest.raises(AppError) as excinfo:
        await _revalidate_checkout_prices(
            session,
            items=cast(
                list[CartItem],
                [
                    _item(first, unit_price="10.00"),
                    _item(second, unit_price="20.00"),
                    _item(stable, unit_price="30.00"),
                ],
            ),
            products_by_id=cast(
                dict[UUID, Product],
                {
                    first: _product(first, base_price="11.00"),
                    second: _product(second, base_price="19.00"),
                    stable: _product(stable, base_price="30.00"),
                },
            ),
            currency="EUR",
        )

    reported = {row["product_id"] for row in excinfo.value.details["items"]}
    assert reported == {str(first), str(second)}


@pytest.mark.asyncio
async def test_currency_rounding_is_applied_before_comparing() -> None:
    """XPF has no minor unit: 10.00 and 10.49 are the same price there."""
    product_id = uuid4()
    session = AsyncMock()
    session.add = Mock()

    await _revalidate_checkout_prices(
        session,
        items=cast(list[CartItem], [_item(product_id, unit_price="10.00")]),
        products_by_id=cast(
            dict[UUID, Product], {product_id: _product(product_id, base_price="10.49")}
        ),
        currency="XPF",
    )

    session.commit.assert_not_awaited()


# -- payment fee ------------------------------------------------------------


@pytest.mark.asyncio
async def test_fee_is_read_from_the_selected_method() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(fee=Decimal("1.25")))

    fee = await _resolve_payment_fee(
        session, payment_method_id=uuid4(), currency="EUR"
    )

    assert fee == Decimal("1.25")


@pytest.mark.asyncio
async def test_no_method_means_no_fee() -> None:
    session = AsyncMock()

    fee = await _resolve_payment_fee(session, payment_method_id=None, currency="EUR")

    assert fee == Decimal("0.00")
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_method_yields_no_fee_and_defers_the_error() -> None:
    """Reporting the bad method id is the payment initiation's job, not ours."""
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    fee = await _resolve_payment_fee(
        session, payment_method_id=uuid4(), currency="EUR"
    )

    assert fee == Decimal("0.00")


@pytest.mark.asyncio
async def test_fee_is_quantized_to_the_currency() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(fee=Decimal("1.49")))

    fee = await _resolve_payment_fee(
        session, payment_method_id=uuid4(), currency="XPF"
    )

    assert fee == Decimal("1")
