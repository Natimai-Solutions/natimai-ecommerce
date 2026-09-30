"""SEED_FRENCH_POLYNESIA_LOGISTICS gates the territory-specific starter data."""

from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.features import initial_data as seed_module

_ALWAYS = (
    "_seed_payment_statuses",
    "_seed_suppliers",
    "_seed_manual_payment_methods",
    "_seed_price_groups",
    "_seed_carriers",
    "_seed_tax_rates",
    "_seed_currency_rates",
    "_seed_shipping_statuses",
    "_seed_security_groups",
    "_seed_legal_identity_settings",
    "_seed_pricing_settings",
    "_seed_customs_free_countries_setting",
)
_POLYNESIA = (
    "_seed_france_papeete_import_corridor",
    "_seed_french_polynesia_geography",
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _stub_all(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    mocks: dict[str, AsyncMock] = {}
    for name in (*_ALWAYS, *_POLYNESIA):
        mocks[name] = AsyncMock()
        monkeypatch.setattr(seed_module, name, mocks[name])
    return mocks


@pytest.mark.anyio
async def test_classic_shop_skips_polynesia_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _stub_all(monkeypatch)
    monkeypatch.setattr(settings, "SEED_FRENCH_POLYNESIA_LOGISTICS", False)

    await seed_module.initial_data(AsyncMock())

    for name in _ALWAYS:
        mocks[name].assert_awaited_once()
    for name in _POLYNESIA:
        mocks[name].assert_not_awaited()


@pytest.mark.anyio
async def test_default_keeps_polynesia_seeds(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _stub_all(monkeypatch)
    monkeypatch.setattr(settings, "SEED_FRENCH_POLYNESIA_LOGISTICS", True)

    await seed_module.initial_data(AsyncMock())

    for name in (*_ALWAYS, *_POLYNESIA):
        mocks[name].assert_awaited_once()
