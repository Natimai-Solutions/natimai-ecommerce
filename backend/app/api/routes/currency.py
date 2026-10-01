"""Public currency endpoints.

Exposes the currently active FX rates so the storefront can display prices in a
visitor's preferred currency. The conversion is **presentational only** — orders
are always computed and billed in the reference currency.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import col, select

from app.api.deps import SessionDep
from app.core.config import settings
from app.features.product.models.currency_rate import CurrencyRate

router = APIRouter(prefix="/currency", tags=["currency"])


def currency_decimals(code: str) -> int:
    """ISO 4217 minor unit (XPF, JPY: 0), as the backend rounds amounts."""
    from app.utils.money import currency_decimals as _decimals

    return _decimals(code)


class DisplayRate(BaseModel):
    """Active rate for one display currency."""

    currency_code: str
    #: Decimals of amounts in this currency (ISO 4217 minor unit) — R7 / L4,
    #: so the fronts round like the backend.
    decimals: int = 2
    # 1 unit of currency_code = rate_to_reference units of the reference currency
    # (e.g. 1 USD = 119.0 XPF) → amount_in_currency = amount_in_reference / rate.
    rate_to_reference: float


class DisplayRatesResponse(BaseModel):
    """Active FX rates available for presentational display."""

    reference_currency: str
    reference_decimals: int = 2
    rates: list[DisplayRate]


@router.get("/display-rates", response_model=DisplayRatesResponse)
async def get_display_rates(session: SessionDep) -> DisplayRatesResponse:
    """Active FX rates (latest per currency) for storefront display conversion."""
    today = date.today()
    statement = (
        select(CurrencyRate)
        .where(
            col(CurrencyRate.is_active).is_(True),
            CurrencyRate.valid_from <= today,
            (
                col(CurrencyRate.valid_until).is_(None)
                | (col(CurrencyRate.valid_until) >= today)
            ),
        )
        .order_by(
            col(CurrencyRate.currency_code),
            col(CurrencyRate.valid_from).desc(),
        )
    )
    result = await session.exec(statement)

    latest_by_code: dict[str, CurrencyRate] = {}
    for rate in result.all():
        # Ordered by valid_from desc → first seen per code is the active one.
        latest_by_code.setdefault(rate.currency_code, rate)

    return DisplayRatesResponse(
        reference_currency=settings.REFERENCE_CURRENCY,
        reference_decimals=currency_decimals(settings.REFERENCE_CURRENCY),
        rates=[
            DisplayRate(
                currency_code=r.currency_code,
                decimals=currency_decimals(r.currency_code),
                rate_to_reference=float(r.rate_to_reference),
            )
            for r in latest_by_code.values()
        ],
    )
