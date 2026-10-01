"""Territory languages, time zone and currencies (R7 / L4-L5)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.currency import get_display_rates
from app.api.routes.system_settings import get_shop_config
from app.api.routes.user_preferences import update_my_preferences
from app.core.config import settings
from app.core.errors import AppError
from app.features.cart.models.cart import Cart
from app.features.product.models.currency_rate import CurrencyRate
from app.features.user.models.user import User
from app.features.user.models.user_preference import UserPreferenceUpdate


@pytest.mark.asyncio
async def test_shop_config_exposes_languages_and_time_zone(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = await get_shop_config(db_session)
    assert config.default_locale == settings.shop_locales[0]
    assert "en" in config.available_locales
    assert config.timezone == settings.SHOP_TIMEZONE
    assert config.default_display_currency

    monkeypatch.setattr(settings, "SHOP_DEFAULT_LOCALE", "en")
    monkeypatch.setattr(settings, "SHOP_TIMEZONE", "Europe/Paris")
    config = await get_shop_config(db_session)
    assert config.available_locales[0] == "en"
    assert config.timezone == "Europe/Paris"


@pytest.mark.asyncio
async def test_display_rates_carry_decimals(db_session: AsyncSession) -> None:
    db_session.add(
        CurrencyRate(
            currency_code="JPY",
            rate_to_reference=Decimal("0.8"),
            valid_from=date(2020, 1, 1),
            is_active=True,
        )
    )
    await db_session.commit()
    rates = await get_display_rates(db_session)
    by_code = {r.currency_code: r.decimals for r in rates.rates}
    assert by_code["JPY"] == 0
    assert rates.reference_decimals == (
        0 if settings.REFERENCE_CURRENCY == "XPF" else 2
    )


@pytest.mark.asyncio
async def test_currency_preference_follows_the_rates_table(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"u-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    user_id = user.id
    db_session.add(
        CurrencyRate(
            currency_code="NZD",
            rate_to_reference=Decimal("70"),
            valid_from=date(2020, 1, 1),
            is_active=True,
        )
    )
    await db_session.commit()
    me = cast(User, SimpleNamespace(id=user_id))
    saved = await update_my_preferences(
        db_session, me, UserPreferenceUpdate(currency_pref="nzd")
    )
    assert saved.currency_pref == "NZD"
    with pytest.raises(AppError):
        await update_my_preferences(
            db_session, me, UserPreferenceUpdate(currency_pref="GBP")
        )


def test_amount_currencies_default_to_the_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REFERENCE_CURRENCY", "EUR")
    assert Cart(user_id=uuid.uuid4()).currency == "EUR"
