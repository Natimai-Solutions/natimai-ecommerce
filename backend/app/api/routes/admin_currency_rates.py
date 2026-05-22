"""Admin endpoints for currency rate management.

GET  /admin/currency-rates        — list all rates (optionally filtered by code)
GET  /admin/currency-rates/{code} — get active rate for a given currency code
PUT  /admin/currency-rates/{code} — create a new rate, close the previous one
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query, status
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.product.models.currency_rate import (
    CurrencyRate,
    CurrencyRatePublic,
    CurrencyRateSource,
    CurrencyRatesPublic,
    CurrencyRateUpsertRequest,
)

router = APIRouter(prefix="/admin/currency-rates", tags=["admin-currency-rates"])


@router.get("", response_model=CurrencyRatesPublic)
async def list_currency_rates(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    code: str | None = Query(
        default=None, description="Filter by currency code (ex: USD)"
    ),
    active_only: bool = Query(
        default=False, description="Only return currently active rates"
    ),
) -> CurrencyRatesPublic:
    """List all currency rates, optionally filtered."""
    today = date.today()
    statement = select(CurrencyRate).where(col(CurrencyRate.is_active).is_(True))

    if code:
        statement = statement.where(CurrencyRate.currency_code == code.upper())

    if active_only:
        statement = statement.where(
            CurrencyRate.valid_from <= today,
            (
                col(CurrencyRate.valid_until).is_(None)
                | (col(CurrencyRate.valid_until) >= today)
            ),
        )

    statement = statement.order_by(
        col(CurrencyRate.currency_code).asc(),
        col(CurrencyRate.valid_from).desc(),
    )
    result = await session.exec(statement)
    rates = list(result.all())
    return CurrencyRatesPublic(
        data=[CurrencyRatePublic.model_validate(r) for r in rates],
        count=len(rates),
    )


@router.get("/{code}", response_model=CurrencyRatePublic)
async def get_active_currency_rate(
    code: str,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> CurrencyRatePublic:
    """Get the currently active rate for a currency code."""
    today = date.today()
    statement = (
        select(CurrencyRate)
        .where(
            CurrencyRate.currency_code == code.upper(),
            col(CurrencyRate.is_active).is_(True),
            CurrencyRate.valid_from <= today,
            (
                col(CurrencyRate.valid_until).is_(None)
                | (col(CurrencyRate.valid_until) >= today)
            ),
        )
        .order_by(col(CurrencyRate.valid_from).desc())
        .limit(1)
    )
    result = await session.exec(statement)
    rate = result.first()
    if rate is None:
        raise AppError(
            code="currency_rate.active.not_found",
            status_code=404,
            message=f"No active currency rate found for '{code.upper()}'",
            details={"currency_code": code.upper()},
        )
    return CurrencyRatePublic.model_validate(rate)


@router.put(
    "/{code}", response_model=CurrencyRatePublic, status_code=status.HTTP_200_OK
)
async def upsert_currency_rate(
    code: str,
    payload: CurrencyRateUpsertRequest,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> CurrencyRatePublic:
    """Create a new rate for the given currency, closing any rate that would overlap.

    This never modifies an existing rate — it always creates a new one and sets
    valid_until on the previous open-ended rate so history is preserved.
    """
    currency_code = code.upper()
    if currency_code == "XPF":
        raise AppError(
            code="currency_rate.reference_currency.unsupported",
            status_code=400,
            message="XPF is the reference currency — no conversion rate needed.",
            details={"currency_code": currency_code},
        )

    # Close any open-ended rate that would overlap with the new valid_from
    overlap_statement = select(CurrencyRate).where(
        CurrencyRate.currency_code == currency_code,
        col(CurrencyRate.is_active).is_(True),
        col(CurrencyRate.valid_until).is_(None),
        CurrencyRate.valid_from < payload.valid_from,
    )
    overlap_result = await session.exec(overlap_statement)
    previous_open = overlap_result.first()
    if previous_open is not None:
        previous_open.valid_until = payload.valid_from
        session.add(previous_open)

    new_rate = CurrencyRate(
        id=uuid.uuid4(),
        currency_code=currency_code,
        rate_to_xpf=payload.rate_to_xpf,
        valid_from=payload.valid_from,
        valid_until=None,
        source=CurrencyRateSource.manual,
        updated_by_user_id=current_user.id,
        is_active=True,
        is_admin_active=True,
    )
    session.add(new_rate)
    await session.commit()
    await session.refresh(new_rate)
    return CurrencyRatePublic.model_validate(new_rate)
