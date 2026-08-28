"""Admin endpoints for catalog fiscality — consumption tax and customs duty.

GET  /admin/tax-rates                      — list rates (filters: territory_code, valid)
POST /admin/tax-rates                      — create a new rate (never mutates existing)
PUT  /admin/tax-rates/{id}                 — update label or set valid_until (close)
PUT  /admin/products/{id}/tax-rate         — assign a tax rate to a product
PUT  /admin/categories/{id}/tax-rate       — assign a tax rate to a category
PUT  /admin/products/{id}/customs-rate     — set/clear a product's customs rate
PUT  /admin/categories/{id}/customs-rate   — set/clear a category's default customs rate
GET  /admin/catalog/publication-report     — what blocks products from the storefront

Invariant: rate_pct is immutable once created. To change a rate create a new one
and set valid_until on the old one to close it.

Customs rates follow the same product → category resolution as tax rates, but
are plain percentages rather than dated records: they are an input of the CAF
price, not a fiscal document line. A product whose rate resolves nowhere is not
publishable (see product/services/publication.py) — the report endpoint exists
to size that backlog before opening the storefront.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.product.crud.category import crud_category
from app.features.product.crud.product import crud_product
from app.features.product.models.category import Category, CategoryPublic
from app.features.product.models.product import Product, ProductPublic
from app.features.product.models.tax_rate import (
    TaxRate,
    TaxRateCreate,
    TaxRatePublic,
    TaxRatesPublic,
    TaxRateUpdate,
)
from app.features.product.services.publication import (
    customs_rate_condition,
    publication_conditions,
    weight_condition,
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
    territory_code: str | None = Query(
        default=None, description="Filter by territory (ex: PF)"
    ),
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

    stmt = stmt.order_by(
        col(TaxRate.territory_code).asc(), col(TaxRate.valid_from).desc()
    )
    result = await session.exec(stmt)
    rates = list(result.all())
    return TaxRatesPublic(
        data=[TaxRatePublic.model_validate(r) for r in rates],
        count=len(rates),
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "/tax-rates", response_model=TaxRatePublic, status_code=status.HTTP_201_CREATED
)
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


# ---------------------------------------------------------------------------
# Customs rates (CAF price input — see product/services/publication.py)
# ---------------------------------------------------------------------------


class CustomsRateAssignBody(BaseModel):
    """Set (or clear, with null) a customs rate percentage."""

    customs_rate_pct: Decimal | None = Field(default=None, ge=0)


@router.put("/products/{product_id}/customs-rate", response_model=ProductPublic)
async def assign_customs_rate_to_product(
    product_id: uuid.UUID,
    payload: CustomsRateAssignBody,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> ProductPublic:
    """Set the product's own customs rate; null falls back to its category."""
    try:
        product = await crud_product.read(session, id=product_id, user=current_user)
    except RecordNotFoundError as exc:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        ) from exc

    product.customs_rate_pct = payload.customs_rate_pct
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return ProductPublic.model_validate(product)


@router.put("/categories/{category_id}/customs-rate", response_model=CategoryPublic)
async def assign_customs_rate_to_category(
    category_id: uuid.UUID,
    payload: CustomsRateAssignBody,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> CategoryPublic:
    """Set the default customs rate inherited by the category's products."""
    try:
        category = await crud_category.read(session, id=category_id, user=current_user)
    except RecordNotFoundError as exc:
        raise AppError(
            code="category.not_found",
            status_code=404,
            message=f"Category '{category_id}' not found",
            details={"category_id": str(category_id)},
        ) from exc

    category.default_customs_rate_pct = payload.customs_rate_pct
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return CategoryPublic.model_validate(category)


# ---------------------------------------------------------------------------
# Publication report
# ---------------------------------------------------------------------------


class CategoryPublicationRow(BaseModel):
    """Per-category publication readiness."""

    category_id: uuid.UUID | None = None
    category_name: str | None = None
    default_customs_rate_pct: Decimal | None = None
    default_tax_rate_id: uuid.UUID | None = None
    product_count: int = 0
    blocked_count: int = 0


class PublicationReport(BaseModel):
    """How much of the enriched catalog is publishable, and what blocks the rest."""

    enriched_count: int = 0
    publishable_count: int = 0
    blocked_customs_rate_unresolved: int = 0
    blocked_weight_missing: int = 0
    categories: list[CategoryPublicationRow] = Field(default_factory=list)


@router.get("/catalog/publication-report", response_model=PublicationReport)
async def get_publication_report(
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> PublicationReport:
    """Size the pre-opening backlog: which products the storefront hides, and why.

    Counts the enriched, active catalog only — a product still waiting for Icecat
    is invisible for an unrelated reason and would drown the signal.
    """
    base_conditions = [
        col(Product.is_active).is_(True),
        col(Product.is_admin_active).is_(True),
        col(Product.is_enriched).is_(True),
    ]

    async def _count(*extra: Any) -> int:
        stmt = select(func.count()).select_from(Product).where(*base_conditions, *extra)
        return int((await session.exec(stmt)).one())

    customs_ok = customs_rate_condition()
    weight_ok = weight_condition()

    enriched_count = await _count()
    publishable_count = await _count(*publication_conditions())
    blocked_customs = await _count(~customs_ok)
    blocked_weight = await _count(~weight_ok)

    category_rows = (
        await session.exec(
            select(
                col(Product.category_id),
                func.count(),
            )
            .where(*base_conditions)
            .group_by(col(Product.category_id))
        )
    ).all()
    blocked_rows = dict(
        (
            await session.exec(
                select(col(Product.category_id), func.count())
                .where(*base_conditions)
                .where(~customs_ok | ~weight_ok)
                .group_by(col(Product.category_id))
            )
        ).all()
    )

    categories: list[CategoryPublicationRow] = []
    for category_id, product_count in category_rows:
        category = (
            await session.get(Category, category_id)
            if category_id is not None
            else None
        )
        categories.append(
            CategoryPublicationRow(
                category_id=category_id,
                category_name=category.name if category is not None else None,
                default_customs_rate_pct=(
                    category.default_customs_rate_pct if category is not None else None
                ),
                default_tax_rate_id=(
                    category.default_tax_rate_id if category is not None else None
                ),
                product_count=int(product_count),
                blocked_count=int(blocked_rows.get(category_id, 0)),
            )
        )

    categories.sort(key=lambda row: (-row.blocked_count, row.category_name or ""))

    return PublicationReport(
        enriched_count=enriched_count,
        publishable_count=publishable_count,
        blocked_customs_rate_unresolved=blocked_customs,
        blocked_weight_missing=blocked_weight,
        categories=categories,
    )
