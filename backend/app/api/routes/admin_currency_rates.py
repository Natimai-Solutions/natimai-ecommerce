"""Admin endpoints for currency rate management.

GET  /admin/currency-rates        — list all rates (optionally filtered by code),
                                    with the display settings (R9 / T2)
GET  /admin/currency-rates/{code} — get active rate for a given currency code
PUT  /admin/currency-rates/{code} — create a new rate, close the previous one
                                    (a new code adds the currency)
PUT  /admin/currency-rates/display-default   — default display currency
PATCH /admin/currency-rates/{code}/display   — offer / hide a display currency
"""

from __future__ import annotations

import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep, module_required
from app.core import runtime_settings
from app.core.config import settings
from app.core.errors import AppError
from app.features.product.models.currency_rate import (
    CurrencyDisplayDefaultRequest,
    CurrencyDisplayRequest,
    CurrencyDisplaySettings,
    CurrencyRate,
    CurrencyRatePublic,
    CurrencyRateSource,
    CurrencyRatesPublic,
    CurrencyRateUpsertRequest,
)
from app.features.system.settings_service import write_setting
from app.tasks.pricing_tasks import schedule_price_refresh

#: ISO 4217 alphabetic code.
_CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")


def _check_code(currency_code: str) -> None:
    if not _CURRENCY_CODE_RE.match(currency_code):
        raise AppError(
            code="currency_rate.code.invalid",
            status_code=400,
            message="Code devise invalide : trois lettres (ISO 4217), ex. USD, EUR",
            details={"currency_code": currency_code},
        )


async def _hidden(session: SessionDep) -> list[str]:
    return [
        str(code).upper()
        for code in await runtime_settings.get("hidden_display_currencies", session)
    ]


async def _display_settings(session: SessionDep) -> CurrencyDisplaySettings:
    default = str(
        await runtime_settings.get("default_display_currency", session)
        or settings.REFERENCE_CURRENCY
    ).upper()
    return CurrencyDisplaySettings(
        reference_currency=settings.REFERENCE_CURRENCY,
        default_display_currency=default,
        hidden_display_currencies=await _hidden(session),
    )


async def _codes_with_active_rate(session: SessionDep) -> set[str]:
    today = date.today()
    codes = (
        await session.exec(
            select(CurrencyRate.currency_code).where(
                col(CurrencyRate.is_active).is_(True),
                CurrencyRate.valid_from <= today,
                (
                    col(CurrencyRate.valid_until).is_(None)
                    | (col(CurrencyRate.valid_until) >= today)
                ),
            )
        )
    ).all()
    return {str(c).upper() for c in codes}


router = APIRouter(
    prefix="/admin/currency-rates",
    tags=["admin-currency-rates"],
    dependencies=[Depends(module_required("currencies"))],
)


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
    display = await _display_settings(session)
    return CurrencyRatesPublic(
        data=[CurrencyRatePublic.model_validate(r) for r in rates],
        count=len(rates),
        reference_currency=display.reference_currency,
        default_display_currency=display.default_display_currency,
        hidden_display_currencies=display.hidden_display_currencies,
    )


@router.put("/display-default", response_model=CurrencyDisplaySettings)
async def set_default_display_currency(
    payload: CurrencyDisplayDefaultRequest,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> CurrencyDisplaySettings:
    """The currency proposed to a visitor who chose none: the reference
    currency, or a currency with an active rate that is offered (R9 / T2)."""
    # Read before any commit expires the ORM user.
    actor = {
        "actor_id": getattr(current_user, "id", None),
        "actor_email": getattr(current_user, "email", None),
    }
    code = payload.currency_code.strip().upper()
    _check_code(code)
    if code != settings.REFERENCE_CURRENCY:
        if code not in await _codes_with_active_rate(session):
            raise AppError(
                code="currency_rate.active.not_found",
                status_code=400,
                message=f"Aucun taux actif pour {code} : ajoutez la devise d'abord",
                details={"currency_code": code},
            )
        if code in await _hidden(session):
            raise AppError(
                code="currency_rate.display.hidden",
                status_code=400,
                message=f"{code} n'est pas proposée au visiteur : activez-la d'abord",
                details={"currency_code": code},
            )
    await write_setting(session, "default_display_currency", code, **actor)
    return await _display_settings(session)


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
    currency_code = code.strip().upper()
    _check_code(currency_code)
    if currency_code == settings.REFERENCE_CURRENCY:
        raise AppError(
            code="currency_rate.reference_currency.unsupported",
            status_code=400,
            message=(
                f"{settings.REFERENCE_CURRENCY} is the reference currency "
                "— no conversion rate needed."
            ),
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
        rate_to_reference=payload.rate_to_reference,
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
    # Every product costed in this currency changes price: refresh the catalog.
    await schedule_price_refresh(reason=f"currency_rate:{currency_code}")
    return CurrencyRatePublic.model_validate(new_rate)


@router.patch("/{code}/display", response_model=CurrencyDisplaySettings)
async def set_currency_display(
    code: str,
    payload: CurrencyDisplayRequest,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> CurrencyDisplaySettings:
    """Offer the currency to the visitor, or hide it (R9 / T2).

    Hiding never touches the rates: the supplier price conversions go on. When
    the hidden currency was the default display currency, the default falls
    back to the reference currency.
    """
    # Read before any commit expires the ORM user.
    actor = {
        "actor_id": getattr(current_user, "id", None),
        "actor_email": getattr(current_user, "email", None),
    }
    currency_code = code.strip().upper()
    _check_code(currency_code)
    if currency_code == settings.REFERENCE_CURRENCY:
        raise AppError(
            code="currency_rate.reference_currency.unsupported",
            status_code=400,
            message=f"{settings.REFERENCE_CURRENCY} est la devise de référence : "
            "toujours proposée.",
            details={"currency_code": currency_code},
        )
    hidden = await _hidden(session)
    if payload.offered:
        hidden = [c for c in hidden if c != currency_code]
    elif currency_code not in hidden:
        hidden.append(currency_code)
    await write_setting(
        session, "hidden_display_currencies", ", ".join(hidden), **actor
    )
    display = await _display_settings(session)
    if not payload.offered and display.default_display_currency == currency_code:
        await write_setting(
            session, "default_display_currency", settings.REFERENCE_CURRENCY, **actor
        )
        display = await _display_settings(session)
    return display
