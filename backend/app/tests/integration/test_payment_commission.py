"""Integration tests (real DB): the payment commission grossed into the
price — the setting, its validation, both price paths agreeing, and the
catalogue re-priced when the owner changes it."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import app.tasks.pricing_tasks as pricing_tasks
from app.api.routes.system_settings import admin_upsert_setting
from app.core.errors import AppError
from app.features.product.models.product import PricingMode, Product
from app.features.product.services.pricing import (
    PricingContext,
    calculate_sale_price,
)
from app.features.product.services.pricing_parameters import (
    PAYMENT_COMMISSION_KEY,
    apply_payment_commission,
    load_pricing_parameters,
    parse_pricing_value,
)
from app.features.system.models.system_setting import (
    SystemSetting,
    SystemSettingUpdate,
)
from app.features.user.models.user import User
from app.tasks.pricing_tasks import refresh_sale_prices


def test_commission_maths_and_parsing() -> None:
    # 2 % commission: the shop nets 100 000 out of 102 040.82.
    assert apply_payment_commission(Decimal("100000.00"), Decimal("2")) == Decimal(
        "102040.82"
    )
    assert apply_payment_commission(Decimal("100000.00"), Decimal("0")) == Decimal(
        "100000.00"
    )
    assert parse_pricing_value(PAYMENT_COMMISSION_KEY, " 1,5 % ") == Decimal("1.5")
    for bad in ("abc", "-1", "100", "150", ""):
        with pytest.raises(ValueError):
            parse_pricing_value(PAYMENT_COMMISSION_KEY, bad)


@pytest.mark.asyncio
async def test_the_setting_drives_both_price_paths_and_reprices_the_catalogue(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    product = Product(
        name="Local sans commission",
        pricing_mode=PricingMode.DOMESTIC,
        cost_amount=Decimal("10000"),
        cost_currency="XPF",
        margin_rate_pct=Decimal("30"),
        is_enriched=True,
    )
    db_session.add_all([admin, product])
    await db_session.flush()
    admin_view = cast(User, SimpleNamespace(id=admin.id))
    product_id = product.id
    await db_session.commit()

    # No setting yet: the parameters read as their defaults, prices unchanged.
    assert (await load_pricing_parameters(db_session)).payment_commission_pct == 0
    product = cast(Product, await db_session.get(Product, product_id))
    before = await calculate_sale_price(db_session, product)
    assert before > 0

    # The owner types a bad value: refused, nothing stored.
    with pytest.raises(AppError) as refused:
        await admin_upsert_setting(
            PAYMENT_COMMISSION_KEY,
            SystemSettingUpdate(value="120"),
            db_session,
            admin_view,
        )
    assert refused.value.code == "system_setting.invalid_value"

    # A valid one is stored and queues a catalogue refresh.
    scheduled: list[Any] = []

    async def _schedule(**kwargs: Any) -> str | None:
        scheduled.append(kwargs)
        return "job"

    monkeypatch.setattr(pricing_tasks, "schedule_price_refresh", _schedule)
    saved = await admin_upsert_setting(
        PAYMENT_COMMISSION_KEY, SystemSettingUpdate(value="2"), db_session, admin_view
    )
    assert saved.value == "2"
    assert scheduled == [{"reason": f"system_setting:{PAYMENT_COMMISSION_KEY}"}]
    row = (
        await db_session.exec(
            select(SystemSetting).where(SystemSetting.key == PAYMENT_COMMISSION_KEY)
        )
    ).first()
    assert row is not None and row.value == "2"

    # Both price paths gross the price up identically.
    product = cast(Product, await db_session.get(Product, product_id))
    single = await calculate_sale_price(db_session, product)
    assert single == apply_payment_commission(before, Decimal("2"))
    context = await PricingContext.load(db_session)
    assert context.payment_commission_pct == Decimal("2")
    assert context.price(product) == single

    # The refresh task (what the queued job runs) materialises the new price.
    await refresh_sale_prices(db_session, product_ids=[product_id])
    product = cast(Product, await db_session.get(Product, product_id))
    assert product.sale_price_cached == single


@pytest.mark.asyncio
async def test_the_fx_safety_margin_cushions_foreign_costs_only(
    db_session: AsyncSession,
) -> None:
    from datetime import date, timedelta

    from app.features.product.models.currency_rate import (
        CurrencyRate,
        CurrencyRateSource,
    )
    from app.features.product.services.pricing_parameters import (
        FX_SAFETY_MARGIN_KEY,
    )

    db_session.add(
        CurrencyRate(
            currency_code="USD",
            rate_to_reference=Decimal("110"),
            valid_from=date.today() - timedelta(days=30),
            source=CurrencyRateSource.manual,
            is_active=True,
            is_admin_active=True,
        )
    )
    foreign = Product(
        name="Coût en USD",
        pricing_mode=PricingMode.DOMESTIC,
        cost_amount=Decimal("100"),
        cost_currency="USD",
        margin_rate_pct=Decimal("0"),
        tax_rate_id=None,
    )
    local = Product(
        name="Coût en XPF",
        pricing_mode=PricingMode.DOMESTIC,
        cost_amount=Decimal("11000"),
        cost_currency="XPF",
        margin_rate_pct=Decimal("0"),
    )
    db_session.add_all([foreign, local])
    await db_session.flush()
    foreign_id, local_id = foreign.id, local.id
    await db_session.commit()

    foreign = cast(Product, await db_session.get(Product, foreign_id))
    local = cast(Product, await db_session.get(Product, local_id))
    # Same cost once converted: same price before any margin.
    base_foreign = await calculate_sale_price(db_session, foreign)
    base_local = await calculate_sale_price(db_session, local)
    assert base_foreign == base_local

    db_session.add(SystemSetting(key=FX_SAFETY_MARGIN_KEY, value="3"))
    await db_session.commit()
    foreign = cast(Product, await db_session.get(Product, foreign_id))
    local = cast(Product, await db_session.get(Product, local_id))
    with_margin = await calculate_sale_price(db_session, foreign)
    assert with_margin == (base_foreign * Decimal("1.03")).quantize(Decimal("0.01"))
    # The XPF cost carries no exchange risk: untouched.
    assert await calculate_sale_price(db_session, local) == base_local
    context = await PricingContext.load(db_session)
    assert context.fx_safety_margin_pct == Decimal("3")
    assert context.price(foreign) == with_margin
    assert context.price(local) == base_local
