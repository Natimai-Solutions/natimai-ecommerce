"""Unit: the territory profile fills the settings the environment leaves unset.

``TERRITORY_PROFILE=FR`` must be enough to run a shop in metropolitan France
(EUR, TVA, no Polynesian starter data); any value set explicitly wins.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.core.territory import FR, PF, get_profile
from app.features import initial_data
from app.features.invoice.services.pdf import _format_amount


def _settings(**overrides: Any) -> Settings:
    """Settings from explicit values only: the developer's .env must not leak in."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_default_profile_keeps_the_historical_polynesian_values() -> None:
    s = _settings()
    assert s.TERRITORY_PROFILE == "PF"
    assert s.REFERENCE_CURRENCY == "XPF"
    assert s.TAX_TERRITORY_CODE == "PF"
    assert s.DEFAULT_TAX_CODE == "TVA_NORMALE"
    assert s.INVOICE_FEES_TAX_CODE == "TVA_NORMALE"
    assert s.SHOP_COUNTRY_CODE == "PF"
    assert s.SEED_FRENCH_POLYNESIA_LOGISTICS is True
    assert s.territory_profile is PF


def test_france_profile_switches_currency_tax_and_starter_data() -> None:
    s = _settings(TERRITORY_PROFILE="FR")
    assert s.REFERENCE_CURRENCY == "EUR"
    assert s.PAYZEN_CURRENCY == "EUR"
    assert s.TAX_TERRITORY_CODE == "FR"
    assert s.DEFAULT_TAX_CODE == "TVA_NORMALE"
    assert s.INVOICE_FEES_TAX_CODE == "TVA_NORMALE"
    assert s.SHOP_COUNTRY_CODE == "FR"
    assert s.SEED_FRENCH_POLYNESIA_LOGISTICS is False
    assert s.territory_profile is FR


def test_an_explicit_setting_wins_over_the_profile() -> None:
    s = _settings(
        TERRITORY_PROFILE="FR",
        DEFAULT_TAX_CODE="TVA_REDUITE",
        SEED_FRENCH_POLYNESIA_LOGISTICS=True,
    )
    assert s.DEFAULT_TAX_CODE == "TVA_REDUITE"
    assert s.SEED_FRENCH_POLYNESIA_LOGISTICS is True
    assert s.REFERENCE_CURRENCY == "EUR"  # still from the profile


def test_simple_shop_mode_flag() -> None:
    assert _settings().is_simple_shop is False
    assert _settings(SHOP_MODE="simple").is_simple_shop is True


def test_profiles_are_self_consistent() -> None:
    for profile in (PF, FR):
        assert get_profile(profile.code) is profile
        codes = {spec.code for spec in profile.tax_rates}
        assert profile.default_tax_code in codes
        assert all(code != profile.currency for code, _ in profile.currency_rates)


def _session_adding() -> tuple[Any, list[Any]]:
    added: list[Any] = []
    result = MagicMock()
    result.first.return_value = None
    session = MagicMock()
    session.exec = AsyncMock(return_value=result)
    session.add = lambda row: added.append(row)
    session.commit = AsyncMock()
    return session, added


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_tax_rates_are_seeded_from_the_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(initial_data, "settings", _settings(TERRITORY_PROFILE="FR"))
    session, added = _session_adding()
    await initial_data._seed_tax_rates(session)
    assert {(r.code, r.territory_code) for r in added} == {
        (spec.code, "FR") for spec in FR.tax_rates
    }
    assert next(r for r in added if r.code == "TVA_NORMALE").rate_pct == Decimal(
        "20.00"
    )


@pytest.mark.anyio
async def test_currency_rates_never_include_the_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(initial_data, "settings", _settings(TERRITORY_PROFILE="FR"))
    session, added = _session_adding()
    await initial_data._seed_currency_rates(session)
    assert {r.currency_code for r in added} == {"USD", "XPF"}


def test_invoice_amounts_follow_the_currency_minor_unit() -> None:
    from app.features.invoice.services.pdf import (
        _CURRENCY_SEPARATOR as cur,
    )
    from app.features.invoice.services.pdf import (
        _THOUSANDS_SEPARATOR as thou,
    )

    assert _format_amount(Decimal("1234.7"), "XPF") == f"1{thou}235{cur}XPF"
    assert _format_amount(Decimal("1234.5"), "EUR") == f"1{thou}234,50{cur}EUR"


def test_shop_config_endpoint_exposes_no_secret() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/system/config")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "shop_mode",
        "territory_profile",
        "territory_label",
        "reference_currency",
        "country_code",
        "tax_territory_code",
        "shop_name",
    }
    assert body["reference_currency"] == SimpleNamespace(**body).reference_currency
