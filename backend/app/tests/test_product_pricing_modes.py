"""Unit tests for the pricing modes and the margin resolution.

Three modes (``Product.pricing_mode``):

* ``import`` — the historical CAF formula (covered by test_product_pricing_caf);
* ``domestic`` — cost × margin × tax, no customs nor import freight;
* ``fixed`` — ``base_price`` is the tax-inclusive price typed by the admin.

The margin resolves product → category → price group. Mock sessions, no DB.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.features.product.models.product import PricingMode
from app.features.product.services.pricing import (
    calculate_price_by_mode,
    calculate_sale_price,
    resolve_margin_rate_pct,
    resolve_pricing_mode,
)
from app.features.product.services.publication import (
    CUSTOMS_RATE_UNRESOLVED,
    FIXED_PRICE_MISSING,
    WEIGHT_MISSING,
    publication_blockers,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _product(
    *,
    pricing_mode: Any = PricingMode.IMPORT,
    cost_amount: str = "100000",
    base_price: str = "0",
    customs_rate_pct: str | None = "5",
    margin_rate_pct: str | None = None,
    weight: float | None = 2.5,
    category_id: Any = None,
) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        pricing_mode=pricing_mode,
        cost_amount=Decimal(cost_amount),
        cost_currency="XPF",
        customs_rate_pct=(
            Decimal(customs_rate_pct) if customs_rate_pct is not None else None
        ),
        margin_rate_pct=(
            Decimal(margin_rate_pct) if margin_rate_pct is not None else None
        ),
        weight=weight,
        dimensions_length=None,
        dimensions_width=None,
        dimensions_height=None,
        base_price=Decimal(base_price),
        tax_rate_id=None,
        category_id=category_id,
    )


def _group(margin_rate_pct: str = "30") -> Any:
    return SimpleNamespace(margin_rate_pct=Decimal(margin_rate_pct))


def _route(price_per_kg: str = "1500") -> Any:
    return SimpleNamespace(
        id=uuid4(),
        price_per_kg=Decimal(price_per_kg),
        base_price=Decimal("0"),
        mode="air",
        eta_days=5,
        service_level="rapide",
        carbon_footprint_kg_co2e=None,
        route_metadata=None,
    )


def _session(*, tax_rate_pct: str = "16", category_margin: str | None = None) -> Any:
    tax_rate = SimpleNamespace(
        is_active=True,
        rate_pct=Decimal(tax_rate_pct),
        valid_from=date(2020, 1, 1),
        valid_until=None,
    )
    category = SimpleNamespace(
        default_customs_rate_pct=None,
        default_tax_rate_id=None,
        default_margin_rate_pct=(
            Decimal(category_margin) if category_margin is not None else None
        ),
    )

    async def _exec(_stmt: Any) -> Any:
        result = MagicMock()
        result.first.return_value = tax_rate
        return result

    session = MagicMock()
    session.exec = AsyncMock(side_effect=_exec)
    session.get = AsyncMock(return_value=category)
    return session


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# resolve_pricing_mode
# ---------------------------------------------------------------------------


def _ns(**fields: Any) -> Any:
    return SimpleNamespace(**fields)


def test_missing_or_unknown_mode_is_the_import_mode() -> None:
    """Never a cheaper mode by accident: unknown defaults to the full formula."""
    assert resolve_pricing_mode(_ns()) is PricingMode.IMPORT
    assert resolve_pricing_mode(_ns(pricing_mode="???")) is PricingMode.IMPORT
    assert resolve_pricing_mode(_ns(pricing_mode="fixed")) is PricingMode.FIXED
    assert (
        resolve_pricing_mode(_ns(pricing_mode=PricingMode.DOMESTIC))
        is PricingMode.DOMESTIC
    )


# ---------------------------------------------------------------------------
# resolve_margin_rate_pct
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_margin_falls_back_to_the_price_group() -> None:
    product = _product()
    assert await resolve_margin_rate_pct(
        _session(), product, group=_group("25")
    ) == Decimal("25")


@pytest.mark.anyio
async def test_margin_defaults_to_30_without_any_group() -> None:
    assert await resolve_margin_rate_pct(_session(), _product(), group=None) == Decimal(
        "30.00"
    )


@pytest.mark.anyio
async def test_category_margin_wins_over_the_group() -> None:
    product = _product(category_id=uuid4())
    session = _session(category_margin="40")

    assert await resolve_margin_rate_pct(session, product, group=_group("25")) == (
        Decimal("40")
    )


@pytest.mark.anyio
async def test_product_margin_wins_over_the_category() -> None:
    product = _product(category_id=uuid4(), margin_rate_pct="12")
    session = _session(category_margin="40")

    assert await resolve_margin_rate_pct(session, product, group=_group("25")) == (
        Decimal("12")
    )


# ---------------------------------------------------------------------------
# calculate_sale_price per mode
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fixed_mode_returns_base_price_untouched() -> None:
    """The admin typed a TTC price: no cost, no margin, no tax on top."""
    product = _product(
        pricing_mode=PricingMode.FIXED, base_price="49990", cost_amount="1"
    )

    price = await calculate_sale_price(_session(), product, group=_group())

    assert price == Decimal("49990.00")


@pytest.mark.anyio
async def test_fixed_mode_ignores_import_routes() -> None:
    product = _product(pricing_mode=PricingMode.FIXED, base_price="49990")

    price = await calculate_sale_price(
        _session(), product, group=_group(), import_route=_route()
    )

    assert price == Decimal("49990.00")


@pytest.mark.anyio
async def test_domestic_mode_has_no_customs_and_no_freight() -> None:
    """cost=100 000, margin=30 %, TGC=16 % → 100 000 × 1.30 × 1.16."""
    product = _product(pricing_mode=PricingMode.DOMESTIC, customs_rate_pct="20")

    price = await calculate_sale_price(
        _session(), product, group=_group(), import_route=_route()
    )

    assert price == _q(Decimal("100000") * Decimal("1.30") * Decimal("1.16"))


@pytest.mark.anyio
async def test_domestic_mode_uses_the_category_margin() -> None:
    product = _product(pricing_mode=PricingMode.DOMESTIC, category_id=uuid4())
    session = _session(category_margin="10")

    price = await calculate_sale_price(session, product, group=_group("30"))

    assert price == _q(Decimal("100000") * Decimal("1.10") * Decimal("1.16"))


@pytest.mark.anyio
async def test_import_mode_uses_the_product_margin_override() -> None:
    product = _product(margin_rate_pct="10")

    price = await calculate_sale_price(_session(), product, group=_group("30"))

    assert price == _q(
        Decimal("100000") * Decimal("1.05") * Decimal("1.10") * Decimal("1.16")
    )


@pytest.mark.anyio
async def test_domestic_is_cheaper_than_import_for_the_same_cost() -> None:
    session = _session()
    domestic = await calculate_sale_price(
        session, _product(pricing_mode=PricingMode.DOMESTIC), group=_group()
    )
    imported = await calculate_sale_price(
        session, _product(), group=_group(), import_route=_route()
    )

    assert domestic < imported


# ---------------------------------------------------------------------------
# calculate_price_by_mode
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_only_import_products_have_shipping_modes() -> None:
    session = _session()
    routes = [_route()]

    assert (
        await calculate_price_by_mode(
            session, _product(pricing_mode=PricingMode.DOMESTIC), routes, group=_group()
        )
        == []
    )
    assert (
        await calculate_price_by_mode(
            session,
            _product(pricing_mode=PricingMode.FIXED, base_price="10"),
            routes,
            group=_group(),
        )
        == []
    )
    assert (
        len(await calculate_price_by_mode(session, _product(), routes, group=_group()))
        == 1
    )


# ---------------------------------------------------------------------------
# publication_blockers per mode
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_import_mode_keeps_the_customs_and_weight_gate() -> None:
    product = _product(customs_rate_pct=None, weight=None)

    assert await publication_blockers(_session(), product) == [
        CUSTOMS_RATE_UNRESOLVED,
        WEIGHT_MISSING,
    ]


@pytest.mark.anyio
async def test_domestic_mode_needs_neither_customs_nor_weight() -> None:
    product = _product(
        pricing_mode=PricingMode.DOMESTIC, customs_rate_pct=None, weight=None
    )

    assert await publication_blockers(_session(), product) == []


@pytest.mark.anyio
async def test_fixed_mode_needs_a_positive_price_only() -> None:
    session = _session()
    unpriced = _product(
        pricing_mode=PricingMode.FIXED,
        base_price="0",
        customs_rate_pct=None,
        weight=None,
    )
    priced = _product(
        pricing_mode=PricingMode.FIXED,
        base_price="1500",
        customs_rate_pct=None,
        weight=None,
    )

    assert await publication_blockers(session, unpriced) == [FIXED_PRICE_MISSING]
    assert await publication_blockers(session, priced) == []
