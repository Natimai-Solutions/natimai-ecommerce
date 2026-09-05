"""Integration: materialized storefront prices (``products.sale_price_cached``).

Real Postgres. Three things must hold:

* ``PricingContext.price`` gives, to the cent, what ``calculate_sale_price``
  (the reference, query-per-product) gives — every mode, every resolution;
* a product written through the CRUD (admin screens, syncs, imports) leaves
  with its cached price set;
* the refresh task recomputes the catalog after a parameter change, and
  leaves a product unpriced when its currency has no rate.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import admin_create_product, admin_update_product
from app.features.product.models.category import Category
from app.features.product.models.currency_rate import CurrencyRate, CurrencyRateSource
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductCreate,
    ProductUpdate,
)
from app.features.product.models.tax_rate import TaxRate
from app.features.product.services.pricing import (
    PricingContext,
    calculate_sale_price,
)
from app.features.user.models.user import User
from app.tasks.pricing_tasks import refresh_sale_prices

TODAY = date.today()


async def _seed_admin(session: AsyncSession) -> User:
    admin = User(
        email="admin@test.local", is_active=True, is_superuser=True, hashed_password="x"
    )
    session.add(admin)
    await session.flush()
    return admin


def _tax(code: str, rate: str) -> TaxRate:
    return TaxRate(
        code=code,
        label=code,
        rate_pct=Decimal(rate),
        territory_code="PF",
        valid_from=TODAY - timedelta(days=30),
        is_active=True,
        is_admin_active=True,
    )


def _fx(code: str, rate: str, *, valid_from: date | None = None) -> CurrencyRate:
    return CurrencyRate(
        currency_code=code,
        rate_to_reference=Decimal(rate),
        valid_from=valid_from or (TODAY - timedelta(days=30)),
        source=CurrencyRateSource.manual,
        is_active=True,
        is_admin_active=True,
    )


@pytest.mark.asyncio
async def test_context_price_matches_the_reference_formula(
    db_session: AsyncSession,
) -> None:
    normal, reduced = _tax("TGC_NORMAL", "16"), _tax("TGC_REDUCED", "5")
    db_session.add_all([normal, reduced, _fx("EUR", "119.33")])
    await db_session.flush()
    category = Category(
        name="Portables",
        default_margin_rate_pct=Decimal("12.5"),
        default_customs_rate_pct=Decimal("7"),
        default_tax_rate_id=reduced.id,
    )
    db_session.add(category)
    await db_session.flush()

    products = [
        Product(
            name="TTC fixé", pricing_mode=PricingMode.FIXED, base_price=Decimal("2990")
        ),
        Product(
            name="Local, marge et taxe de la catégorie, coût en EUR",
            pricing_mode=PricingMode.DOMESTIC,
            cost_amount=Decimal("100"),
            cost_currency="EUR",
            category_id=category.id,
        ),
        Product(
            name="Import, douane propre, marge catégorie",
            pricing_mode=PricingMode.IMPORT,
            cost_amount=Decimal("50000"),
            cost_currency="XPF",
            customs_rate_pct=Decimal("3"),
            category_id=category.id,
            weight=1.2,
        ),
        Product(
            name="Import, marge propre, sans catégorie (taxe du territoire)",
            pricing_mode=PricingMode.IMPORT,
            cost_amount=Decimal("80000"),
            cost_currency="XPF",
            margin_rate_pct=Decimal("40"),
            tax_rate_id=normal.id,
        ),
    ]
    db_session.add_all(products)
    await db_session.commit()
    for product in products:
        await db_session.refresh(product)

    context = await PricingContext.load(db_session)
    for product in products:
        reference = await calculate_sale_price(db_session, product)
        assert context.price(product) == reference, product.name
        assert reference > 0


@pytest.mark.asyncio
async def test_admin_writes_leave_the_cached_price_set(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)

    created = await admin_create_product(
        session=db_session,
        current_user=admin,
        payload=ProductCreate(
            name="Câble HDMI",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("1500"),
        ),
    )
    assert created.sale_price_cached == Decimal("1500.00")
    assert created.sale_price_cached_at is not None
    created_id = created.id
    await db_session.refresh(admin)  # expired by the commit above

    await admin_update_product(
        session=db_session,
        current_user=admin,
        product_id=created_id,
        payload=ProductUpdate(base_price=Decimal("1990")),
    )
    refreshed = await db_session.get(Product, created_id)
    assert refreshed is not None
    assert refreshed.sale_price_cached == Decimal("1990.00")


@pytest.mark.asyncio
async def test_refresh_task_follows_a_currency_rate_change(
    db_session: AsyncSession,
) -> None:
    old_rate = _fx("EUR", "119.33")
    db_session.add(old_rate)
    euro = Product(
        name="Coûté en euros",
        pricing_mode=PricingMode.DOMESTIC,
        cost_amount=Decimal("100"),
        cost_currency="EUR",
        margin_rate_pct=Decimal("0"),
    )
    dollar = Product(
        name="Coûté en dollars, sans taux",
        pricing_mode=PricingMode.DOMESTIC,
        cost_amount=Decimal("100"),
        cost_currency="USD",
    )
    db_session.add_all([euro, dollar])
    await db_session.commit()
    await db_session.refresh(euro)
    euro_id = euro.id

    stats = await refresh_sale_prices(db_session)
    assert stats == {"total": 2, "priced": 1, "unpriced": 1, "batches": 1}
    await db_session.refresh(euro)
    await db_session.refresh(dollar)
    assert euro.sale_price_cached == Decimal("11933.00")  # no tax rate seeded → 0 %
    assert dollar.sale_price_cached is None
    assert dollar.sale_price_cached_at is not None

    # The admin posts a new rate (what upsert_currency_rate does): old closed.
    old_rate.valid_until = TODAY
    db_session.add(old_rate)
    db_session.add(_fx("EUR", "120", valid_from=TODAY))
    await db_session.commit()

    await refresh_sale_prices(db_session, product_ids=[euro_id], batch_size=1)
    await db_session.refresh(euro)
    assert euro.sale_price_cached == Decimal("12000.00")
