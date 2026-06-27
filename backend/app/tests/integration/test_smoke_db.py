"""Smoke test: validates the real-Postgres integration harness end-to-end."""

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.currency_rate import CurrencyRate


@pytest.mark.asyncio
async def test_currency_rate_persists_and_reads_back(db_session: AsyncSession) -> None:
    db_session.add(
        CurrencyRate(
            currency_code="USD",
            rate_to_reference=Decimal("119.0"),
            valid_from=date(2026, 1, 1),
        )
    )
    await db_session.commit()

    result = await db_session.exec(
        select(CurrencyRate).where(col(CurrencyRate.currency_code) == "USD")
    )
    rows = result.all()
    assert len(rows) == 1
    assert rows[0].rate_to_reference == Decimal("119.0")
