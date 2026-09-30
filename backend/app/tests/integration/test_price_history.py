"""Integration tests (real DB): the price journal — one line per change of
the storefront price, with its cause, from both write paths."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import (
    admin_create_product,
    admin_product_price_history,
    admin_update_product,
)
from app.features.product.models.currency_rate import (
    CurrencyRate,
    CurrencyRateSource,
)
from app.features.product.models.price_history import (
    REASON_PRODUCT_WRITE,
    ProductPriceEntry,
    price_change_entry,
)
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductCreate,
    ProductUpdate,
)
from app.features.user.models.user import User
from app.tasks.pricing_tasks import refresh_sale_prices


def test_only_a_change_makes_an_entry() -> None:
    pid = uuid.uuid4()
    assert price_change_entry(pid, Decimal("10"), Decimal("10"), reason="x") is None
    assert price_change_entry(pid, None, None, reason="x") is None
    entry = price_change_entry(pid, None, Decimal("10"), reason="nightly")
    assert entry is not None and entry.reason == "nightly" and entry.old_price is None


@pytest.mark.asyncio
async def test_every_price_move_is_journaled_with_its_cause(
    db_session: AsyncSession,
) -> None:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    rate = CurrencyRate(
        currency_code="EUR",
        rate_to_reference=Decimal("119.33"),
        valid_from=date.today() - timedelta(days=30),
        source=CurrencyRateSource.manual,
        is_active=True,
        is_admin_active=True,
    )
    db_session.add_all([admin, rate])
    await db_session.flush()
    admin_view = cast(User, SimpleNamespace(id=admin.id, is_superuser=True))
    rate_id = rate.id
    await db_session.commit()

    # Admin write: created at 1 500 (from nothing), then edited to 1 990.
    created = await admin_create_product(
        session=db_session,
        current_user=admin_view,
        payload=ProductCreate(
            name="Câble HDMI",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("1500"),
        ),
    )
    product_id = created.id
    await admin_update_product(
        session=db_session,
        current_user=admin_view,
        product_id=product_id,
        payload=ProductUpdate(base_price=Decimal("1990")),
    )
    # A write that leaves the price alone adds nothing.
    await admin_update_product(
        session=db_session,
        current_user=admin_view,
        product_id=product_id,
        payload=ProductUpdate(description="Câble 2 m"),
    )
    history = await admin_product_price_history(db_session, admin_view, product_id)
    assert [(e.old_price, e.new_price, e.reason) for e in history] == [
        (Decimal("1500.00"), Decimal("1990.00"), REASON_PRODUCT_WRITE),
        (None, Decimal("1500.00"), REASON_PRODUCT_WRITE),
    ]

    # Bulk refresh: a currency rate change re-prices a euro product under
    # the rate's reason; an unchanged product gets no line.
    euro = Product(
        name="Coûté en euros",
        pricing_mode=PricingMode.DOMESTIC,
        cost_amount=Decimal("100"),
        cost_currency="EUR",
        margin_rate_pct=Decimal("0"),
    )
    db_session.add(euro)
    await db_session.flush()
    euro_id = euro.id
    await db_session.commit()
    await refresh_sale_prices(db_session, product_ids=[euro_id], reason="admin_inline")
    rate = cast(CurrencyRate, await db_session.get(CurrencyRate, rate_id))
    rate.valid_until = date.today()
    db_session.add(rate)
    db_session.add(
        CurrencyRate(
            currency_code="EUR",
            rate_to_reference=Decimal("120"),
            valid_from=date.today(),
            source=CurrencyRateSource.manual,
            is_active=True,
            is_admin_active=True,
        )
    )
    await db_session.commit()
    await refresh_sale_prices(
        db_session, product_ids=[euro_id, product_id], reason="currency_rate:EUR"
    )
    euro_history = await admin_product_price_history(db_session, admin_view, euro_id)
    assert [(e.old_price, e.new_price, e.reason) for e in euro_history] == [
        (Decimal("11933.00"), Decimal("12000.00"), "currency_rate:EUR"),
        (None, Decimal("11933.00"), "admin_inline"),
    ]
    # The fixed-price product did not move: still two lines.
    count = (
        await db_session.exec(
            select(ProductPriceEntry).where(ProductPriceEntry.product_id == product_id)
        )
    ).all()
    assert len(count) == 2
