"""Re-checking supplier stock at checkout instead of trusting a snapshot.

``product.supplier_quantity`` is refreshed by a cron every two hours. The
checkout reserved against it and nothing else, so on drop-shipped stock a
two-hour window separated what the customer was told from what the supplier
actually had.

The hard rule of this feature is asymmetry: a supplier that *answers* and says
the stock is gone must change the outcome; a supplier that cannot be reached
must never block a sale.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import settings
from app.features.integrations.services import checkout_availability
from app.features.integrations.services.checkout_availability import (
    refresh_supplier_availability,
)
from app.features.product.models.product import Product


def _product(
    *,
    sku: str | None = "SKU-1",
    quantity: str = "5",
    supplier: str | None = "ingram_micro",
    managed: bool = True,
) -> Any:
    return SimpleNamespace(
        id=f"product-{sku}",
        supplier_sku=sku,
        supplier_name=supplier,
        is_supplier_managed=managed,
        supplier_quantity=Decimal(quantity),
    )


def _install_adapter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pricing: dict[str, Any] | None = None,
    raises: Exception | None = None,
    configured: bool = True,
    sync_enabled: bool = True,
    hangs: bool = False,
) -> AsyncMock:
    async def _fetch(_skus: list[str]) -> dict[str, Any]:
        if hangs:
            await asyncio.sleep(3600)
        if raises is not None:
            raise raises
        return pricing or {}

    fetch = AsyncMock(side_effect=_fetch)
    adapter = SimpleNamespace(
        is_configured=lambda: configured,
        is_sync_enabled=lambda: sync_enabled,
        fetch_price_and_availability=fetch,
    )
    monkeypatch.setattr(
        checkout_availability, "resolve_adapter", AsyncMock(return_value=adapter)
    )
    return fetch


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHECKOUT_SUPPLIER_AVAILABILITY_CHECK", True)
    monkeypatch.setattr(settings, "CHECKOUT_SUPPLIER_CHECK_TIMEOUT_SECONDS", 8.0)


def _session() -> Any:
    session = AsyncMock()
    session.add = Mock()
    return session


@pytest.mark.asyncio
async def test_a_fresher_quantity_replaces_the_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_adapter(
        monkeypatch, pricing={"SKU-1": SimpleNamespace(quantity=2, price=100)}
    )
    product = _product(quantity="5")
    session = _session()

    refreshed = await refresh_supplier_availability(
        session, cast(list[Product], [product])
    )

    assert refreshed == {"SKU-1": Decimal("2")}
    assert product.supplier_quantity == Decimal("2")
    session.add.assert_called_once_with(product)


@pytest.mark.asyncio
async def test_an_unchanged_quantity_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_adapter(
        monkeypatch, pricing={"SKU-1": SimpleNamespace(quantity=5, price=100)}
    )
    session = _session()

    await refresh_supplier_availability(
        session, cast(list[Product], [_product(quantity="5")])
    )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_a_sku_the_supplier_no_longer_knows_is_zeroed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent from the response means it cannot be sourced right now."""
    _install_adapter(monkeypatch, pricing={"SKU-1": SimpleNamespace(quantity=3)})
    known = _product(sku="SKU-1", quantity="5")
    vanished = _product(sku="SKU-2", quantity="7")
    session = _session()

    refreshed = await refresh_supplier_availability(
        session, cast(list[Product], [known, vanished])
    )

    assert refreshed["SKU-2"] == Decimal("0")
    assert vanished.supplier_quantity == Decimal("0")


@pytest.mark.asyncio
async def test_a_supplier_outage_never_blocks_the_sale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refusing every order while Ingram is down is worse than the risk."""
    _install_adapter(monkeypatch, raises=RuntimeError("502 Bad Gateway"))
    product = _product(quantity="5")
    session = _session()

    refreshed = await refresh_supplier_availability(
        session, cast(list[Product], [product])
    )

    assert refreshed == {}
    assert product.supplier_quantity == Decimal("5")  # snapshot stands
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_a_slow_supplier_is_abandoned_not_waited_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This runs on the checkout critical path, not in a background job."""
    monkeypatch.setattr(settings, "CHECKOUT_SUPPLIER_CHECK_TIMEOUT_SECONDS", 0.01)
    _install_adapter(monkeypatch, hangs=True)
    product = _product(quantity="5")

    refreshed = await refresh_supplier_availability(
        _session(), cast(list[Product], [product])
    )

    assert refreshed == {}
    assert product.supplier_quantity == Decimal("5")


@pytest.mark.asyncio
async def test_the_check_can_be_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CHECKOUT_SUPPLIER_AVAILABILITY_CHECK", False)
    fetch = _install_adapter(
        monkeypatch, pricing={"SKU-1": SimpleNamespace(quantity=0)}
    )

    refreshed = await refresh_supplier_availability(
        _session(), cast(list[Product], [_product()])
    )

    assert refreshed == {}
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_locally_stocked_products_are_not_looked_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch = _install_adapter(monkeypatch, pricing={})

    await refresh_supplier_availability(
        _session(),
        cast(
            list[Product],
            [
                _product(managed=False),
                _product(sku=None),
                _product(supplier=None),
            ],
        ),
    )

    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_supplier_without_live_api_keeps_its_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual and file suppliers resolve to no adapter: the snapshot stands."""
    monkeypatch.setattr(
        checkout_availability, "resolve_adapter", AsyncMock(return_value=None)
    )
    product = _product(supplier="generic_fr", quantity="5")
    session = _session()

    refreshed = await refresh_supplier_availability(
        session, cast(list[Product], [product])
    )

    assert refreshed == {}
    assert product.supplier_quantity == Decimal("5")
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_an_unconfigured_supplier_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No credentials is a deployment state, not an out-of-stock signal."""
    fetch = _install_adapter(monkeypatch, configured=False)
    product = _product(quantity="5")

    refreshed = await refresh_supplier_availability(
        _session(), cast(list[Product], [product])
    )

    assert refreshed == {}
    assert product.supplier_quantity == Decimal("5")
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_supplier_with_syncs_switched_off_is_not_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin switched the supplier's syncs off: the checkout leaves it be."""
    fetch = _install_adapter(monkeypatch, sync_enabled=False)
    product = _product(quantity="5")

    refreshed = await refresh_supplier_availability(
        _session(), cast(list[Product], [product])
    )

    assert refreshed == {}
    assert product.supplier_quantity == Decimal("5")
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_call_covers_every_line_of_the_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One request per checkout, not one per line — the quota is finite."""
    fetch = _install_adapter(
        monkeypatch,
        pricing={
            "SKU-1": SimpleNamespace(quantity=1),
            "SKU-2": SimpleNamespace(quantity=2),
            "SKU-3": SimpleNamespace(quantity=3),
        },
    )

    await refresh_supplier_availability(
        _session(),
        cast(
            list[Product],
            [_product(sku="SKU-1"), _product(sku="SKU-2"), _product(sku="SKU-3")],
        ),
    )

    fetch.assert_awaited_once()
    assert fetch.await_args is not None
    assert sorted(fetch.await_args.args[0]) == ["SKU-1", "SKU-2", "SKU-3"]
