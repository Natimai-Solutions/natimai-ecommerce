"""Unit tests for the cart CRUD (audit item Q3).

Le panier porte deux choses qui finissent dans une commande : le **total**
quantifié dans la devise du panier, et le **snapshot de change** posé sur la
ligne au moment de l'ajout. Les deux sont recopiés au checkout, donc une erreur
ici ne se voit qu'une fois la commande créée.

La base est simulée : seules la logique et les effets de bord (add/commit)
sont testés, pas le SQL.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.features.cart.crud.cart as cart_crud_module
from app.features.base.crud import RecordNotFoundError
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.product.services.pricing import CurrencyRateMissing


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _session(rows: list[Any] | None = None, *, get: Any = None) -> Any:
    """Session simulée : un `exec` servant `rows`, un `get` servant `get`."""
    result = MagicMock()
    result.first.return_value = (rows or [None])[0] if rows else None
    result.all.return_value = rows or []

    session = MagicMock()
    session.exec = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=get)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _cart(
    *,
    currency: str = "XPF",
    is_active: bool = True,
    is_admin_active: bool = True,
    is_checked_out: bool = False,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        currency=currency,
        is_active=is_active,
        is_admin_active=is_admin_active,
        is_checked_out=is_checked_out,
        total_amount=Decimal("0.00"),
    )


def _item(*, unit_price: str, quantity: int) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        unit_price=Decimal(unit_price),
        quantity=quantity,
        is_active=True,
    )


def _product(*, base_price: str = "1000", cost_currency: str | None = None) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        base_price=Decimal(base_price),
        cost_currency=cost_currency,
    )


# ---------------------------------------------------------------------------
# get_or_create_active_cart
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_existing_active_cart_is_reused_without_writing() -> None:
    existing = _cart()
    session = _session([existing])

    cart = await crud_cart.get_or_create_active_cart(session, user_id=uuid.uuid4())

    assert cart is existing
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_a_missing_cart_is_created_empty_in_the_requested_currency() -> None:
    session = _session([])
    user_id = uuid.uuid4()

    cart = await crud_cart.get_or_create_active_cart(
        session, user_id=user_id, currency="EUR"
    )

    assert cart.user_id == user_id
    assert cart.currency == "EUR"
    assert cart.total_amount == Decimal("0.00")
    assert cart.is_checked_out is False
    session.add.assert_called_once_with(cart)
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# sync_total
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sync_total_sums_lines_and_quantizes_in_the_cart_currency() -> None:
    """XPF n'a pas de sous-unité : le total est arrondi à l'entier."""
    cart = _cart(currency="XPF")
    session = _session(
        [
            _item(unit_price="1200.40", quantity=2),
            _item(unit_price="99.30", quantity=1),
        ],
        get=cart,
    )

    total = await crud_cart.sync_total(session, cart_id=cart.id)

    # 1200.40 × 2 + 99.30 = 2500.10 → 2500 en XPF
    assert total == Decimal("2500")
    assert cart.total_amount == Decimal("2500")
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_sync_total_keeps_cents_in_a_subunit_currency() -> None:
    cart = _cart(currency="EUR")
    session = _session([_item(unit_price="10.005", quantity=1)], get=cart)

    assert await crud_cart.sync_total(session, cart_id=cart.id) == Decimal("10.01")


@pytest.mark.anyio
async def test_sync_total_on_an_empty_cart_is_zero() -> None:
    cart = _cart()
    session = _session([], get=cart)

    assert await crud_cart.sync_total(session, cart_id=cart.id) == Decimal("0")


@pytest.mark.parametrize(
    "cart",
    [
        None,
        _cart(is_active=False),
        _cart(is_admin_active=False),
        _cart(is_checked_out=True),
    ],
    ids=["missing", "inactive", "admin-disabled", "already-checked-out"],
)
@pytest.mark.anyio
async def test_sync_total_refuses_a_cart_that_is_not_open(cart: Any) -> None:
    """Un panier déjà commandé ne doit plus voir son total bouger."""
    session = _session([], get=cart)

    with pytest.raises(RecordNotFoundError):
        await crud_cart.sync_total(session, cart_id=uuid.uuid4())

    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# add_or_increment — snapshot de change
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_adding_a_new_product_snapshots_no_fx_in_reference_currency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le taux n'est figé que s'il y a eu conversion : sinon il n'apprend rien."""
    monkeypatch.setattr(
        cart_crud_module,
        "convert_to_reference_currency",
        AsyncMock(return_value=(Decimal("1"), Decimal("1"))),
    )
    product = _product(base_price="1500", cost_currency="XPF")
    session = _session([])
    cart_id = uuid.uuid4()

    item = await crud_cart_item.add_or_increment(
        session, cart_id=cart_id, product=product, quantity=2
    )

    assert item.cart_id == cart_id
    assert item.product_id == product.id
    assert item.quantity == 2
    assert item.unit_price == Decimal("1500")
    assert item.fx_rate_used is None
    assert item.fx_source_currency is None
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_adding_a_foreign_currency_product_freezes_the_rate_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cart_crud_module,
        "convert_to_reference_currency",
        AsyncMock(return_value=(Decimal("119.33"), Decimal("119.33"))),
    )
    product = _product(cost_currency="EUR")

    item = await crud_cart_item.add_or_increment(
        _session([]), cart_id=uuid.uuid4(), product=product, quantity=1
    )

    assert item.fx_rate_used == Decimal("119.33")
    assert item.fx_source_currency == "EUR"


@pytest.mark.anyio
async def test_a_missing_currency_rate_does_not_block_adding_to_the_cart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le snapshot reste nul, mais le client peut toujours acheter."""
    monkeypatch.setattr(
        cart_crud_module,
        "convert_to_reference_currency",
        AsyncMock(side_effect=CurrencyRateMissing("USD")),
    )
    product = _product(cost_currency="USD")

    item = await crud_cart_item.add_or_increment(
        _session([]), cart_id=uuid.uuid4(), product=product, quantity=1
    )

    assert item.fx_rate_used is None
    assert item.fx_source_currency is None
    assert item.quantity == 1


@pytest.mark.anyio
async def test_adding_a_product_already_in_the_cart_increments_and_refreshes_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le prix unitaire suit le catalogue, il n'est pas figé au premier ajout."""
    monkeypatch.setattr(
        cart_crud_module,
        "convert_to_reference_currency",
        AsyncMock(return_value=(Decimal("1"), Decimal("1"))),
    )
    existing: Any = SimpleNamespace(
        id=uuid.uuid4(),
        quantity=2,
        unit_price=Decimal("900"),
        fx_rate_used=None,
        fx_source_currency=None,
    )
    product = _product(base_price="1000", cost_currency="XPF")
    session = _session([existing])

    item = await crud_cart_item.add_or_increment(
        session, cart_id=uuid.uuid4(), product=product, quantity=3
    )

    assert item is existing
    assert item.quantity == 5
    assert item.unit_price == Decimal("1000")
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_active_item_for_user — la garde d'appartenance
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_an_item_of_someone_else_cart_is_not_returned() -> None:
    session = _session([])

    found = await crud_cart_item.get_active_item_for_user(
        session, item_id=uuid.uuid4(), user_id=uuid.uuid4()
    )

    assert found is None


@pytest.mark.anyio
async def test_item_lookup_is_scoped_to_the_user_and_to_an_open_cart() -> None:
    """C'est cette jointure qui empêche de modifier la ligne d'un autre client."""
    item = _item(unit_price="1000", quantity=1)
    session = _session([item])

    found = await crud_cart_item.get_active_item_for_user(
        session, item_id=item.id, user_id=uuid.uuid4()
    )

    assert found is item
    where = str(session.exec.await_args.args[0].whereclause)
    assert "carts.user_id" in where
    assert "carts.is_checked_out" in where


# ---------------------------------------------------------------------------
# update_quantity / deactivate_item / clear_cart
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_quantity_replaces_instead_of_adding() -> None:
    item = _item(unit_price="1000", quantity=7)
    session = _session([])

    updated = await crud_cart_item.update_quantity(session, item=item, quantity=2)

    assert updated.quantity == 2
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_deactivate_item_is_a_soft_delete() -> None:
    item = _item(unit_price="1000", quantity=1)
    session = _session([])

    await crud_cart_item.deactivate_item(session, item=item)

    assert item.is_active is False
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_clear_cart_deactivates_every_line_and_returns_the_count() -> None:
    items = [_item(unit_price="1000", quantity=1) for _ in range(3)]
    session = _session(items)

    removed = await crud_cart_item.clear_cart(session, cart_id=uuid.uuid4())

    assert removed == 3
    assert all(item.is_active is False for item in items)
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_clearing_an_empty_cart_still_commits_and_returns_zero() -> None:
    session = _session([])

    assert await crud_cart_item.clear_cart(session, cart_id=uuid.uuid4()) == 0
