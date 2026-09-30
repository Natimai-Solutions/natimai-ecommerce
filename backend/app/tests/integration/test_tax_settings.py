"""The shop's default rate and fees rate, chosen in base (real database).

A shop outside Polynesia defines its own rates and picks, from the admin,
which one applies by default and which one taxes the fees — no redeploy.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_tax_rates
from app.api.routes.admin_tax_rates import (
    TaxSettingsUpdate,
    get_tax_settings,
    update_tax_settings,
)
from app.core.config import settings
from app.core.errors import AppError
from app.features.invoice.services.invoice_service import _resolve_fees_tax_rate_pct
from app.features.product.models.product import PricingMode, Product
from app.features.product.models.tax_rate import TaxRate
from app.features.product.services.pricing import (
    PricingContext,
    calculate_sale_price,
    resolve_tax_rate,
)
from app.features.product.services.tax_settings import load_tax_codes

TODAY = date.today()
ADMIN = cast(Any, SimpleNamespace(id=None, is_superuser=True))


def _rate(code: str, pct: str, *, territory: str | None = None) -> TaxRate:
    return TaxRate(
        code=code,
        label=code.replace("_", " ").title(),
        rate_pct=Decimal(pct),
        territory_code=territory or settings.TAX_TERRITORY_CODE,
        valid_from=TODAY - timedelta(days=1),
        is_active=True,
        is_admin_active=True,
    )


@pytest.fixture(autouse=True)
def _no_refresh(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    refresh = AsyncMock()
    monkeypatch.setattr(admin_tax_rates, "schedule_price_refresh", refresh)
    return refresh


@pytest.mark.asyncio
async def test_the_admin_chooses_the_default_and_fees_rates(
    db_session: AsyncSession, _no_refresh: AsyncMock
) -> None:
    db_session.add_all(
        [
            _rate("TVA_NORMALE", "16"),
            _rate("STANDARD_VAT", "21"),
            _rate("SERVICES_VAT", "9"),
        ]
    )
    product = Product(
        name="Article sans taux",
        pricing_mode=PricingMode.DOMESTIC,
        cost_amount=Decimal("1000"),
        cost_currency=settings.REFERENCE_CURRENCY,
        margin_rate_pct=Decimal("0"),
    )
    db_session.add(product)
    await db_session.commit()

    before = await get_tax_settings(cast(Any, db_session), ADMIN)
    assert before.default_code == "TVA_NORMALE"
    assert before.default_rate is not None
    assert before.default_rate.rate_pct == Decimal("16.00")

    after = await update_tax_settings(
        TaxSettingsUpdate(default_code="standard_vat", fees_code="SERVICES_VAT"),
        cast(Any, db_session),
        ADMIN,
    )
    assert (after.default_code, after.fees_code) == ("STANDARD_VAT", "SERVICES_VAT")
    _no_refresh.assert_awaited_once()

    await db_session.refresh(product)
    rate = await resolve_tax_rate(db_session, product)
    assert rate is not None and rate.code == "STANDARD_VAT"
    context = await PricingContext.load(db_session)
    reference = await calculate_sale_price(db_session, product)
    assert context.price(product) == reference
    assert await _resolve_fees_tax_rate_pct(db_session) == Decimal("9.00")


@pytest.mark.asyncio
async def test_a_code_without_a_rate_in_force_is_refused(
    db_session: AsyncSession,
) -> None:
    closed = _rate("OLD_VAT", "18")
    closed.valid_until = TODAY - timedelta(days=1)
    closed.valid_from = TODAY - timedelta(days=60)
    db_session.add_all([_rate("TVA_NORMALE", "16"), closed])
    await db_session.commit()

    for code in ("OLD_VAT", "NOWHERE"):
        with pytest.raises(AppError) as refused:
            await update_tax_settings(
                TaxSettingsUpdate(default_code=code, fees_code="TVA_NORMALE"),
                cast(Any, db_session),
                ADMIN,
            )
        assert refused.value.code == "tax_rate.code_not_active"


@pytest.mark.asyncio
async def test_an_environment_still_naming_tgc_codes_keeps_working(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DEFAULT_TAX_CODE", "TGC_NORMAL")
    monkeypatch.setattr(settings, "INVOICE_FEES_TAX_CODE", "TGC_REDUIT")
    codes = await load_tax_codes(db_session)
    assert (codes.default_code, codes.fees_code) == ("TVA_NORMALE", "TVA_REDUITE")
