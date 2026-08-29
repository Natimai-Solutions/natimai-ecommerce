"""Unit tests for the storefront publication guard (audit items F1 / F5).

Covers the customs-rate resolution (product → category) and the blockers that
keep a mispriced product off the storefront. Mock sessions throughout — no DB.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.features.product.services.pricing import (
    calculate_sale_price,
    resolve_customs_rate_pct,
)
from app.features.product.services.publication import (
    CUSTOMS_RATE_UNRESOLVED,
    WEIGHT_MISSING,
    publication_blockers,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _product(
    *,
    customs_rate_pct: str | None = None,
    category_id: Any = None,
    weight: float | None = 2.5,
) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        cost_amount=Decimal("100000"),
        cost_currency="XPF",
        customs_rate_pct=(
            Decimal(customs_rate_pct) if customs_rate_pct is not None else None
        ),
        weight=weight,
        dimensions_length=None,
        dimensions_width=None,
        dimensions_height=None,
        base_price=Decimal("0"),
        tax_rate_id=None,
        category_id=category_id,
    )


def _group(margin_rate_pct: str = "30") -> Any:
    return SimpleNamespace(margin_rate_pct=Decimal(margin_rate_pct))


def _session(*, category_customs_rate: str | None = None) -> Any:
    """Session whose ``get`` returns a category carrying (or not) a customs default."""
    category = SimpleNamespace(
        default_customs_rate_pct=(
            Decimal(category_customs_rate)
            if category_customs_rate is not None
            else None
        ),
        default_tax_rate_id=None,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=category)
    return session


# ---------------------------------------------------------------------------
# resolve_customs_rate_pct
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_product_rate_wins_over_category() -> None:
    product = _product(customs_rate_pct="12", category_id=uuid4())
    session = _session(category_customs_rate="30")

    assert await resolve_customs_rate_pct(session, product) == Decimal("12")


@pytest.mark.anyio
async def test_falls_back_to_category_default() -> None:
    product = _product(category_id=uuid4())
    session = _session(category_customs_rate="30")

    assert await resolve_customs_rate_pct(session, product) == Decimal("30")


@pytest.mark.anyio
async def test_explicit_zero_on_product_is_kept() -> None:
    """An exempt product must not silently inherit its category's rate."""
    product = _product(customs_rate_pct="0", category_id=uuid4())
    session = _session(category_customs_rate="30")

    assert await resolve_customs_rate_pct(session, product) == Decimal("0")


@pytest.mark.anyio
async def test_unresolved_returns_none_not_zero() -> None:
    """The whole point of F1: no rate anywhere is 'unknown', never 0 %."""
    product = _product(category_id=uuid4())
    session = _session(category_customs_rate=None)

    assert await resolve_customs_rate_pct(session, product) is None


@pytest.mark.anyio
async def test_unresolved_without_category() -> None:
    product = _product(category_id=None)
    session = _session()

    assert await resolve_customs_rate_pct(session, product) is None


@pytest.mark.anyio
async def test_sale_price_uses_the_category_rate() -> None:
    """A product with no own rate is priced with its category's, not with 0 %."""
    product = _product(category_id=uuid4())
    tax_rate = SimpleNamespace(
        is_active=True,
        rate_pct=Decimal("16"),
        valid_from=date(2020, 1, 1),
        valid_until=None,
    )
    category = SimpleNamespace(
        default_customs_rate_pct=Decimal("5"), default_tax_rate_id=None
    )

    async def _exec(_stmt: Any) -> Any:
        result = MagicMock()
        result.first.return_value = tax_rate
        return result

    session = MagicMock()
    session.exec = AsyncMock(side_effect=_exec)
    session.get = AsyncMock(return_value=category)

    price = await calculate_sale_price(session, product, group=_group())

    # 100 000 × 1.05 × 1.30 × 1.16 — the same figure as an explicit 5 % product.
    assert price == Decimal("158340.00")


# ---------------------------------------------------------------------------
# publication_blockers
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_no_blockers_when_rate_and_weight_are_present() -> None:
    product = _product(customs_rate_pct="5", weight=2.5)

    assert await publication_blockers(_session(), product) == []


@pytest.mark.anyio
async def test_blocks_on_unresolved_customs_rate() -> None:
    product = _product(category_id=uuid4(), weight=2.5)

    blockers = await publication_blockers(_session(), product)

    assert blockers == [CUSTOMS_RATE_UNRESOLVED]


@pytest.mark.anyio
async def test_blocks_on_missing_weight() -> None:
    product = _product(customs_rate_pct="5", weight=None)

    assert await publication_blockers(_session(), product) == [WEIGHT_MISSING]


@pytest.mark.anyio
async def test_blocks_on_zero_weight() -> None:
    """Weight 0 is the same silent zero as no weight at all: freight vanishes."""
    product = _product(customs_rate_pct="5", weight=0.0)

    assert await publication_blockers(_session(), product) == [WEIGHT_MISSING]


@pytest.mark.anyio
async def test_reports_every_blocker_at_once() -> None:
    product = _product(category_id=uuid4(), weight=None)

    blockers = await publication_blockers(_session(), product)

    assert blockers == [CUSTOMS_RATE_UNRESOLVED, WEIGHT_MISSING]


@pytest.mark.anyio
async def test_missing_dimensions_alone_do_not_block() -> None:
    """Dimensions fall back to the real weight — under-billing, not a wrong zero."""
    product = _product(customs_rate_pct="5", weight=2.5)

    assert await publication_blockers(_session(), product) == []
