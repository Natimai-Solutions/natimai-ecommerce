"""Admin endpoints for tax-rate management.

GET  /admin/tax-rates                      — list rates (filters: territory_code, valid)
POST /admin/tax-rates                      — create a new rate (never mutates existing)
PUT  /admin/tax-rates/{id}                 — update label or set valid_until (close)
PUT  /admin/products/{id}/tax-rate         — assign a tax rate to a product
PUT  /admin/categories/{id}/tax-rate       — assign a tax rate to a category

Invariant: rate_pct is immutable once created. To change a rate create a new one
and set valid_until on the old one to close it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Query, status
from pydantic import BaseModel
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.product.crud.category import crud_category
from app.features.product.crud.product import crud_product
from app.features.product.models.category import CategoryPublic
from app.features.product.models.product import ProductPublic
from app.features.product.models.tax_rate import (
    TaxRate,
    TaxRateCreate,
    TaxRatePublic,
    TaxRatesPublic,
    TaxRateUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-tax-rates"])


class TaxRateAssignBody(BaseModel):
    """Assign (or clear) a tax rate by id."""

    tax_rate_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_active_tax_rate(session: SessionDep, tax_rate_id: uuid.UUID) -> TaxRate:
    rate = await session.get(TaxRate, tax_rate_id)
    if rate is None or not rate.is_active:
        raise AppError(
            code="tax_rate.not_found",
            status_code=404,
            message=f"Tax rate '{tax_rate_id}' not found",
            details={"tax_rate_id": str(tax_rate_id)},
        )
    return rate


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("/tax-rates", response_model=TaxRatesPublic)
async def list_tax_rates(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    territory_code: str | None = Query(default=None, description="Filter by territory (ex: PF)"),
    valid: bool | None = Query(
        default=None, description="true → active today, false → already expired"
    ),
) -> TaxRatesPublic:
    """List tax rates with optional filters."""
    today = date.today()
    stmt = select(TaxRate).where(col(TaxRate.is_active).is_(True))

    if territory_code:
        stmt = stmt.where(TaxRate.territory_code == territory_code.upper())

    if valid is True:
        stmt = stmt.where(
            TaxRate.valid_from <= today,
            col(TaxRate.valid_until).is_(None) | (col(TaxRate.valid_until) >= today),
        )
    elif valid is False:
        stmt = stmt.where(
            col(TaxRate.valid_until).is_not(None),
            col(TaxRate.valid_until) < today,
        )

    stmt = stmt.order_by(col(TaxRate.territory_code).asc(), col(TaxRate.valid_from).desc())
    result = await session.exec(stmt)
    rates = list(result.all())
    return TaxRatesPublic(
        data=[TaxRatePublic.model_validate(r) for r in rates],
        count=len(rates),
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("/tax-rates", response_model=TaxRatePublic, status_code=status.HTTP_201_CREATED)
async def create_tax_rate(
    payload: TaxRateCreate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> TaxRatePublic:
    """Create a new tax rate (never modifies an existing one)."""
    rate = TaxRate(
        id=uuid.uuid4(),
        code=payload.code,
        label=payload.label,
        rate_pct=payload.rate_pct,
        territory_code=payload.territory_code,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        is_active=True,
        is_admin_active=True,
        created_by_id=current_user.id,
    )
    session.add(rate)
    await session.commit()
    await session.refresh(rate)
    logger.info(
        "Tax rate created: code=%s rate_pct=%s territory=%s created_by=%s",
        rate.code,
        rate.rate_pct,
        rate.territory_code,
        current_user.id,
    )
    return TaxRatePublic.model_validate(rate)


# ---------------------------------------------------------------------------
# Update (label or valid_until only — rate_pct is immutable)
# ---------------------------------------------------------------------------


@router.put("/tax-rates/{tax_rate_id}", response_model=TaxRatePublic)
async def update_tax_rate(
    tax_rate_id: uuid.UUID,
    payload: TaxRateUpdate,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> TaxRatePublic:
    """Update label or set valid_until to close a tax rate.

    Modifying rate_pct is forbidden — create a new rate with a new valid_from instead.
    """
    rate = await _get_active_tax_rate(session, tax_rate_id)

    if payload.label is not None:
        rate.label = payload.label
    if payload.valid_until is not None:
        if payload.valid_until < rate.valid_from:
            raise AppError(
                code="tax_rate.invalid_valid_until",
                status_code=400,
                message="valid_until cannot be before valid_from",
                details={
                    "tax_rate_id": str(tax_rate_id),
                    "valid_from": str(rate.valid_from),
                    "valid_until": str(payload.valid_until),
                },
            )
        rate.valid_until = payload.valid_until

    session.add(rate)
    await session.commit()
    await session.refresh(rate)
    return TaxRatePublic.model_validate(rate)


# ---------------------------------------------------------------------------
# Assign to product
# ---------------------------------------------------------------------------


@router.put("/products/{product_id}/tax-rate", response_model=ProductPublic)
async def assign_tax_rate_to_product(
    product_id: uuid.UUID,
    payload: TaxRateAssignBody,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> ProductPublic:
    """Assign (or clear) the tax rate on a product."""
    if payload.tax_rate_id is not None:
        await _get_active_tax_rate(session, payload.tax_rate_id)

    try:
        product = await crud_product.read(session, id=product_id, user=current_user)
    except RecordNotFoundError as exc:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        ) from exc

    product.tax_rate_id = payload.tax_rate_id
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return ProductPublic.model_validate(product)


# ---------------------------------------------------------------------------
# Assign to category
# ---------------------------------------------------------------------------


@router.put("/categories/{category_id}/tax-rate", response_model=CategoryPublic)
async def assign_tax_rate_to_category(
    category_id: uuid.UUID,
    payload: TaxRateAssignBody,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> CategoryPublic:
    """Assign (or clear) the default tax rate on a category."""
    if payload.tax_rate_id is not None:
        await _get_active_tax_rate(session, payload.tax_rate_id)

    try:
        category = await crud_category.read(session, id=category_id, user=current_user)
    except RecordNotFoundError as exc:
        raise AppError(
            code="category.not_found",
            status_code=404,
            message=f"Category '{category_id}' not found",
            details={"category_id": str(category_id)},
        ) from exc

    category.default_tax_rate_id = payload.tax_rate_id
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return CategoryPublic.model_validate(category)
