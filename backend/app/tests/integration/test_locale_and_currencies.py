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


@pytest.mark.asyncio
async def test_languages_are_settings_of_the_base(db_session: AsyncSession) -> None:
    """R9 / T2: the default language and the offered languages are edited in
    Admin → Paramètres → Affichage; the environment is only the fallback."""
    from app.core.i18n import get_offered_locales
    from app.features.system.settings_service import write_setting

    await write_setting(db_session, "shop_default_locale", "en")
    await write_setting(db_session, "shop_locales", "fr")
    config = await get_shop_config(db_session)
    # The default is always offered, first.
    assert config.default_locale == "en"
    assert config.available_locales == ["en", "fr"]
    assert await get_offered_locales(db_session) == ["en", "fr"]

    with pytest.raises(AppError) as refused:
        await write_setting(db_session, "shop_locales", "fr, es")
    assert refused.value.code == "system_setting.invalid_value"

    await write_setting(db_session, "shop_default_locale", "")
    await write_setting(db_session, "shop_locales", "")
    config = await get_shop_config(db_session)
    assert config.available_locales == settings.shop_locales


@pytest.mark.asyncio
async def test_display_currencies_are_added_offered_hidden_and_defaulted(
    db_session: AsyncSession,
) -> None:
    """R9 / T2: Admin → Taux de change adds a currency, hides it from the
    visitor (rates untouched) and picks the default display currency."""
    from app.api.routes.admin_currency_rates import (
        list_currency_rates,
        set_currency_display,
        set_default_display_currency,
        upsert_currency_rate,
    )
    from app.features.product.models.currency_rate import (
        CurrencyDisplayDefaultRequest,
        CurrencyDisplayRequest,
        CurrencyRateUpsertRequest,
    )

    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    db_session.add(admin)
    await db_session.flush()
    admin = cast(User, SimpleNamespace(id=admin.id, email=admin.email))

    with pytest.raises(AppError) as bad:
        await upsert_currency_rate(
            "us$",
            CurrencyRateUpsertRequest(
                rate_to_reference=Decimal("110"), valid_from=date(2020, 1, 1)
            ),
            db_session,
            admin,
        )
    assert bad.value.code == "currency_rate.code.invalid"

    # Adding a currency is a first rate on a new code.
    await upsert_currency_rate(
        "gbp",
        CurrencyRateUpsertRequest(
            rate_to_reference=Decimal("150"), valid_from=date(2020, 1, 1)
        ),
        db_session,
        admin,
    )
    listed = await list_currency_rates(db_session, admin, code="GBP", active_only=True)
    assert [r.currency_code for r in listed.data] == ["GBP"]
    assert listed.reference_currency == settings.REFERENCE_CURRENCY
    assert "GBP" not in listed.hidden_display_currencies
    assert "GBP" in {
        r.currency_code for r in (await get_display_rates(db_session)).rates
    }

    # Offered → default display currency.
    display = await set_default_display_currency(
        CurrencyDisplayDefaultRequest(currency_code="gbp"), db_session, admin
    )
    assert display.default_display_currency == "GBP"
    assert (await get_shop_config(db_session)).default_display_currency == "GBP"

    # Hidden: the storefront no longer proposes it, the rate stays, the default
    # falls back to the reference currency.
    display = await set_currency_display(
        "GBP", CurrencyDisplayRequest(offered=False), db_session, admin
    )
    assert display.hidden_display_currencies == ["GBP"]
    assert display.default_display_currency == settings.REFERENCE_CURRENCY
    assert "GBP" not in {
        r.currency_code for r in (await get_display_rates(db_session)).rates
    }
    listed = await list_currency_rates(db_session, admin, code="GBP", active_only=True)
    assert len(listed.data) == 1  # the rate is untouched

    with pytest.raises(AppError) as hidden:
        await set_default_display_currency(
            CurrencyDisplayDefaultRequest(currency_code="GBP"), db_session, admin
        )
    assert hidden.value.code == "currency_rate.display.hidden"
    with pytest.raises(AppError) as unknown:
        await set_default_display_currency(
            CurrencyDisplayDefaultRequest(currency_code="CHF"), db_session, admin
        )
    assert unknown.value.code == "currency_rate.active.not_found"

    # A customer cannot keep a hidden currency as preference either.
    from app.api.routes.user_preferences import valid_currencies

    assert "GBP" not in await valid_currencies(db_session)

    display = await set_currency_display(
        "GBP", CurrencyDisplayRequest(offered=True), db_session, admin
    )
    assert display.hidden_display_currencies == []
    with pytest.raises(AppError) as ref:
        await set_currency_display(
            settings.REFERENCE_CURRENCY,
            CurrencyDisplayRequest(offered=False),
            db_session,
            admin,
        )
    assert ref.value.code == "currency_rate.reference_currency.unsupported"
