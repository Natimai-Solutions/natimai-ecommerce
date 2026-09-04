"""Unit tests for CAF-based product pricing (calculate_sale_price).

All tests are synchronous via pytest-anyio/AsyncMock — no live DB needed.
The pricing service is exercised via public functions only.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.features.product.services.pricing import (
    ShippingModePrice,
    _compute_volume_m3,
    calculate_price_by_mode,
    calculate_sale_price,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _product(
    *,
    cost_amount: str = "100000",
    cost_currency: str = "XPF",
    customs_rate_pct: str = "5",
    weight: float | None = 2.5,
    dimensions_length: float | None = None,
    dimensions_width: float | None = None,
    dimensions_height: float | None = None,
    base_price: str = "0",
) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        cost_amount=Decimal(cost_amount),
        cost_currency=cost_currency,
        customs_rate_pct=Decimal(customs_rate_pct),
        weight=weight,
        dimensions_length=dimensions_length,
        dimensions_width=dimensions_width,
        dimensions_height=dimensions_height,
        base_price=Decimal(base_price),
        tax_rate_id=None,
        category_id=None,
    )


def _group(margin_rate_pct: str = "30") -> Any:
    return SimpleNamespace(margin_rate_pct=Decimal(margin_rate_pct))


def _route(
    *,
    price_per_kg: str = "0",
    base_price: str = "0",
    mode: str = "air",
    eta_days: int | None = 5,
    service_level: str | None = "rapide",
    carbon: float | None = None,
    route_metadata: dict[str, Any] | None = None,
) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        price_per_kg=Decimal(price_per_kg),
        base_price=Decimal(base_price),
        mode=mode,
        eta_days=eta_days,
        service_level=service_level,
        carbon_footprint_kg_co2e=carbon,
        route_metadata=route_metadata,
    )


def _mock_session(*, tax_rate_pct: str = "16") -> Any:
    """Session that returns a tax rate with given rate_pct and no currency conversion."""
    tax_rate = SimpleNamespace(
        is_active=True,
        rate_pct=Decimal(tax_rate_pct),
        valid_from=date(2020, 1, 1),
        valid_until=None,
    )

    async def _exec(_stmt: Any) -> Any:
        result = MagicMock()
        result.first.return_value = tax_rate
        return result

    session = MagicMock()
    session.exec = AsyncMock(side_effect=_exec)
    session.get = AsyncMock(return_value=None)
    return session


# ---------------------------------------------------------------------------
# _compute_volume_m3
# ---------------------------------------------------------------------------


def test_compute_volume_m3_returns_none_when_any_dim_missing() -> None:
    p = _product(dimensions_length=30.0, dimensions_width=None, dimensions_height=20.0)
    assert _compute_volume_m3(p) is None


def test_compute_volume_m3_computes_correctly() -> None:
    # 30 cm × 20 cm × 10 cm = 6000 cm³ = 0.006 m³
    p = _product(dimensions_length=30.0, dimensions_width=20.0, dimensions_height=10.0)
    result = _compute_volume_m3(p)
    assert result == Decimal("0.006")


# ---------------------------------------------------------------------------
# calculate_sale_price — no import route (backward-compatible)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_calculate_sale_price_no_route_old_formula() -> None:
    """Without an import route, freight=0 → formula = cost × (1+customs) × (1+margin) × (1+tax).

    cost=100 000, customs=5%, margin=30%, TGC=16%
    expected = 100 000 × 1.05 × 1.30 × 1.16 = 158 262 (rounded)
    """
    product = _product()
    group = _group()
    session = _mock_session()

    price = await calculate_sale_price(session, product, group=group)

    expected = Decimal("100000") * Decimal("1.05") * Decimal("1.30") * Decimal("1.16")
    assert price == expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# calculate_sale_price — with import route (CAF formula)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_calculate_sale_price_caf_with_route_no_volume() -> None:
    """With a route, freight = price_per_kg × actual_weight (no dims available).

    cost=100 000, weight=2.5 kg, freight=1 500/kg → freight=3 750
    insurance=0 (default)
    caf = 100 000 + 3 750 = 103 750
    sale_price = 103 750 × 1.05 × 1.30 × 1.16
    """
    product = _product(weight=2.5)
    group = _group()
    route = _route(price_per_kg="1500", mode="air")
    session = _mock_session()

    price = await calculate_sale_price(
        session, product, group=group, import_route=route
    )

    caf = Decimal("103750")
    expected = caf * Decimal("1.05") * Decimal("1.30") * Decimal("1.16")
    assert price == expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@pytest.mark.anyio
async def test_calculate_sale_price_caf_freight_higher_than_no_route() -> None:
    """A product with freight > 0 must yield a higher price than without route."""
    product = _product(weight=2.5)
    group = _group()
    session = _mock_session()
    route = _route(price_per_kg="1500", mode="air")

    price_no_route = await calculate_sale_price(session, product, group=group)
    price_with_route = await calculate_sale_price(
        session, product, group=group, import_route=route
    )

    assert price_with_route > price_no_route


@pytest.mark.anyio
async def test_calculate_sale_price_caf_volumetric_weight_heavier() -> None:
    """Volumetric weight heavier than actual → larger freight → larger price.

    weight=0.5 kg, dims 40×30×30 cm → vol = 0.036 m³
    volumetric = 0.036 × 167 ≈ 6.012 kg > 0.5 kg actual
    freight = 1 500 × 6.012 = 9 018
    """
    product = _product(
        weight=0.5,
        dimensions_length=40.0,
        dimensions_width=30.0,
        dimensions_height=30.0,
    )
    group = _group()
    route = _route(price_per_kg="1500", mode="air")
    session = _mock_session()

    price_light_actual = await calculate_sale_price(
        session,
        _product(weight=0.5),
        group=group,
        import_route=route,
    )
    price_volumetric = await calculate_sale_price(
        session,
        product,
        group=group,
        import_route=route,
    )

    assert price_volumetric > price_light_actual


# ---------------------------------------------------------------------------
# calculate_price_by_mode
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_calculate_price_by_mode_returns_one_entry_per_route() -> None:
    product = _product(weight=2.5)
    group = _group()
    session = _mock_session()
    routes = [
        _route(price_per_kg="1500", mode="air", service_level="rapide", eta_days=5),
        _route(price_per_kg="300", mode="sea", service_level="economique", eta_days=35),
    ]

    results = await calculate_price_by_mode(session, product, routes, group=group)

    assert len(results) == 2
    assert all(isinstance(r, ShippingModePrice) for r in results)
    by_level = {r.service_level: r for r in results}
    assert "rapide" in by_level
    assert "economique" in by_level


@pytest.mark.anyio
async def test_calculate_price_by_mode_rapide_more_expensive_than_economique() -> None:
    """Air (rapide) has higher freight per kg → higher sale price."""
    product = _product(weight=2.5)
    group = _group()
    session = _mock_session()
    routes = [
        _route(price_per_kg="1500", mode="air", service_level="rapide", eta_days=5),
        _route(price_per_kg="300", mode="sea", service_level="economique", eta_days=35),
    ]

    results = await calculate_price_by_mode(session, product, routes, group=group)
    by_level = {r.service_level: r for r in results}

    assert by_level["rapide"].sale_price > by_level["economique"].sale_price
    assert by_level["rapide"].freight > by_level["economique"].freight
    assert by_level["rapide"].eta_days == 5
    assert by_level["economique"].eta_days == 35


@pytest.mark.anyio
async def test_calculate_price_by_mode_empty_routes_returns_empty() -> None:
    product = _product()
    group = _group()
    session = _mock_session()

    results = await calculate_price_by_mode(session, product, [], group=group)

    assert results == []


# ---------------------------------------------------------------------------
# calculate_sale_price — insurance basis (audit item F4)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_insurance_is_charged_on_cost_plus_freight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The premium covers the goods *and* the freight, so it applies to both.

    cost=100 000, weight=2.5 kg × 1 500/kg → freight=3 750
    insurance = (100 000 + 3 750) × 1 % = 1 037.50
    caf = 100 000 + 3 750 + 1 037.50 = 104 787.50
    """
    monkeypatch.setattr(settings, "INSURANCE_RATE_PCT", 1.0)
    product = _product(weight=2.5)
    group = _group()
    route = _route(price_per_kg="1500", mode="air")
    session = _mock_session()

    price = await calculate_sale_price(
        session, product, group=group, import_route=route
    )

    caf = Decimal("104787.50")
    expected = caf * Decimal("1.05") * Decimal("1.30") * Decimal("1.16")
    assert price == expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@pytest.mark.anyio
async def test_insurance_on_freight_costs_more_than_on_cost_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for F4: insuring the cost only under-prices the freight."""
    monkeypatch.setattr(settings, "INSURANCE_RATE_PCT", 1.0)
    product = _product(weight=2.5)
    group = _group()
    route = _route(price_per_kg="1500", mode="air")
    session = _mock_session()

    price = await calculate_sale_price(
        session, product, group=group, import_route=route
    )

    cost_only_caf = Decimal("100000") * Decimal("1.01") + Decimal("3750")
    cost_only_price = (
        cost_only_caf * Decimal("1.05") * Decimal("1.30") * Decimal("1.16")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert price > cost_only_price
