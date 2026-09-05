"""Unit tests for :class:`PricingContext` — the in-memory price formula.

The context reproduces ``calculate_sale_price`` from preloaded referentials
(parity with the reference is covered by an integration test). Here: each
pricing mode, the margin / customs / tax resolution chain, currency
conversion and the per-session cache. No database.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.features.product.models.product import PricingMode
from app.features.product.models.tax_rate import TaxRate
from app.features.product.services.pricing import (
    CurrencyRateMissing,
    PricingContext,
    _CategoryPricing,
)

TODAY = date(2026, 9, 5)


def _tax(rate: str, **over: Any) -> TaxRate:
    fields: dict[str, Any] = {
        "id": uuid4(),
        "code": "TGC_REDUCED",
        "label": "Taxe",
        "rate_pct": Decimal(rate),
        "territory_code": "PF",
        "valid_from": date(2026, 1, 1),
        "valid_until": None,
        "is_active": True,
    }
    fields.update(over)
    return TaxRate(**fields)


def _context(
    *,
    group_margin: str | None = "20",
    categories: dict[UUID, _CategoryPricing] | None = None,
    taxes: list[TaxRate] | None = None,
    fx: dict[str, str] | None = None,
) -> PricingContext:
    return PricingContext(
        group_margin_rate_pct=Decimal(group_margin) if group_margin else None,
        tax_rates_by_id={t.id: t for t in (taxes or [])},
        default_tax_rate_pct=Decimal("16"),
        fx_rates={k: Decimal(v) for k, v in (fx or {}).items()},
        categories=categories or {},
        insurance_rate_pct=Decimal("0.5"),
        reference_currency="XPF",
        at_date=TODAY,
    )


def _product(**over: Any) -> Any:
    fields: dict[str, Any] = {
        "id": uuid4(),
        "pricing_mode": PricingMode.DOMESTIC,
        "base_price": Decimal("0"),
        "cost_amount": Decimal("1000"),
        "cost_currency": "XPF",
        "customs_rate_pct": None,
        "margin_rate_pct": None,
        "tax_rate_id": None,
        "category_id": None,
        "weight": None,
        "length": None,
        "width": None,
        "height": None,
    }
    fields.update(over)
    return SimpleNamespace(**fields)


def test_fixed_mode_returns_the_typed_price_as_is() -> None:
    context = _context()
    product = _product(
        pricing_mode=PricingMode.FIXED, base_price=Decimal("2990.555"), cost_amount=1
    )
    assert context.price(product) == Decimal("2990.56")


def test_domestic_mode_is_cost_times_margin_times_tax() -> None:
    context = _context(group_margin="20")
    # 1000 × 1.20 × 1.16 = 1392.00
    assert context.price(_product()) == Decimal("1392.00")


def test_import_mode_applies_customs_and_insurance_without_a_route() -> None:
    context = _context(group_margin="20")
    product = _product(pricing_mode=PricingMode.IMPORT, customs_rate_pct=Decimal("5"))
    # CAF = 1000 + 0 + 0.5 % = 1005 ; × 1.05 × 1.20 × 1.16
    expected = (
        Decimal("1005") * Decimal("1.05") * Decimal("1.20") * Decimal("1.16")
    ).quantize(Decimal("0.01"))
    assert context.price(product) == expected


def test_margin_resolves_product_then_category_then_group_then_default() -> None:
    category_id = uuid4()
    with_category = _context(
        group_margin="20",
        categories={category_id: _CategoryPricing(None, Decimal("10"), None)},
    )
    assert with_category.margin_rate_pct(
        _product(margin_rate_pct=Decimal("5"), category_id=category_id)
    ) == Decimal("5")
    assert with_category.margin_rate_pct(_product(category_id=category_id)) == Decimal(
        "10"
    )
    assert with_category.margin_rate_pct(_product()) == Decimal("20")
    assert _context(group_margin=None).margin_rate_pct(_product()) == Decimal("30.00")


def test_customs_resolves_product_then_category_else_none() -> None:
    category_id = uuid4()
    context = _context(
        categories={category_id: _CategoryPricing(Decimal("7"), None, None)}
    )
    assert context.customs_rate_pct(
        _product(customs_rate_pct=Decimal("3"), category_id=category_id)
    ) == Decimal("3")
    assert context.customs_rate_pct(_product(category_id=category_id)) == Decimal("7")
    assert context.customs_rate_pct(_product()) is None


def test_tax_resolves_product_then_category_then_territory_default() -> None:
    own = _tax("5")
    by_category = _tax("13")
    expired = _tax("99", valid_until=date(2026, 6, 30))
    category_id = uuid4()
    context = _context(
        taxes=[own, by_category, expired],
        categories={category_id: _CategoryPricing(None, None, by_category.id)},
    )
    assert context.tax_rate_pct(_product(tax_rate_id=own.id)) == Decimal("5")
    assert context.tax_rate_pct(_product(category_id=category_id)) == Decimal("13")
    # An expired rate on the product falls through to the category, then default.
    assert context.tax_rate_pct(
        _product(tax_rate_id=expired.id, category_id=category_id)
    ) == Decimal("13")
    assert context.tax_rate_pct(_product(tax_rate_id=expired.id)) == Decimal("16")


def test_cost_in_a_foreign_currency_is_converted_or_rejected() -> None:
    context = _context(group_margin="0", fx={"EUR": "119.33"})
    product = _product(cost_amount=Decimal("100"), cost_currency="EUR")
    # 100 EUR → 11933.00 XPF × 1.00 × 1.16
    assert context.price(product) == Decimal("13842.28")

    with pytest.raises(CurrencyRateMissing):
        context.price(_product(cost_currency="USD"))


@pytest.mark.asyncio
async def test_for_session_caches_the_context_for_a_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fresh = _context()
    load = AsyncMock(return_value=fresh)
    monkeypatch.setattr(PricingContext, "load", load)
    session = SimpleNamespace(info={})

    first = await PricingContext.for_session(session)  # type: ignore[arg-type]
    second = await PricingContext.for_session(session)  # type: ignore[arg-type]
    assert first is second is fresh
    assert load.await_count == 1

    # Past the TTL the referentials are reloaded (a rate may have changed).
    fresh.loaded_at = datetime.now(timezone.utc) - timedelta(
        seconds=PricingContext.CACHE_TTL_SECONDS + 1
    )
    await PricingContext.for_session(session)  # type: ignore[arg-type]
    assert load.await_count == 2
