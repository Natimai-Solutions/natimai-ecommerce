"""Test for the public display-rates endpoint."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.routes.currency import get_display_rates


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_display_rates_keeps_latest_per_currency() -> None:
    session = AsyncMock()

    # Ordered by (currency_code, valid_from desc) → newest USD first, then older.
    usd_new = SimpleNamespace(
        currency_code="USD",
        rate_to_reference=Decimal("119.0"),
        valid_from=date(2026, 6, 1),
    )
    usd_old = SimpleNamespace(
        currency_code="USD",
        rate_to_reference=Decimal("115.0"),
        valid_from=date(2026, 1, 1),
    )
    eur = SimpleNamespace(
        currency_code="EUR",
        rate_to_reference=Decimal("131.0"),
        valid_from=date(2026, 6, 1),
    )
    session.exec = AsyncMock(
        return_value=SimpleNamespace(all=Mock(return_value=[eur, usd_new, usd_old]))
    )

    resp = await get_display_rates(session=session)

    assert resp.reference_currency == "XPF"
    by_code = {r.currency_code: r.rate_to_reference for r in resp.rates}
    assert by_code == {"USD": 119.0, "EUR": 131.0}  # newest USD kept, older dropped


@pytest.mark.anyio
async def test_display_rates_empty() -> None:
    session = AsyncMock()
    session.exec = AsyncMock(return_value=SimpleNamespace(all=Mock(return_value=[])))

    resp = await get_display_rates(session=session)

    assert resp.reference_currency == "XPF"
    assert resp.rates == []
