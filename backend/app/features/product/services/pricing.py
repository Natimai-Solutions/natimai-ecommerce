from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.category import Category
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import Product
from app.features.product.models.tax_rate import TaxRate

_MONEY_QUANT = Decimal("0.01")
_DEFAULT_MARGIN_RATE_PCT = Decimal("30.00")
_DEFAULT_TAX_CODE = "TGC_NORMAL"
_DEFAULT_TERRITORY_CODE = "PF"


def _as_decimal(value: object | None, *, default: Decimal = Decimal("0.00")) -> Decimal:
    """Safely coerce an arbitrary value to Decimal."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _quantize_money(value: Decimal) -> Decimal:
    """Normalize monetary values to two decimals."""
    if value < 0:
        value = Decimal("0.00")
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _is_tax_rate_active_for_date(tax_rate: TaxRate, *, at_date: date) -> bool:
    """Check validity window for a tax rate."""
    if tax_rate.valid_from > at_date:
        return False
    if tax_rate.valid_until is not None and tax_rate.valid_until < at_date:
        return False
    return True


def _is_tax_rate_candidate_active(
    tax_rate: object,
    *,
    at_date: date,
) -> bool:
    """Validate tax-rate-like objects defensively for tests and mocks."""
    if tax_rate is None:
        return False

    is_active = getattr(tax_rate, "is_active", False)
    if not isinstance(is_active, bool) or not is_active:
        return False

    valid_from = getattr(tax_rate, "valid_from", None)
    if not isinstance(valid_from, date):
        return False

    valid_until = getattr(tax_rate, "valid_until", None)
    if valid_until is not None and not isinstance(valid_until, date):
        return False

    if valid_from > at_date:
        return False
    if valid_until is not None and valid_until < at_date:
        return False

    return True


async def resolve_default_price_group(session: AsyncSession) -> PriceGroup | None:
    """Resolve the active default price group."""
    statement = (
        select(PriceGroup)
        .where(
            col(PriceGroup.default).is_(True),
            col(PriceGroup.is_active).is_(True),
        )
        .limit(1)
    )
    result = await session.exec(statement)
    default_group = result.first()
    if default_group is not None:
        return default_group

    fallback_statement = (
        select(PriceGroup)
        .where(col(PriceGroup.is_active).is_(True))
        .order_by(col(PriceGroup.created_at).asc())
        .limit(1)
    )
    fallback_result = await session.exec(fallback_statement)
    return fallback_result.first()


async def resolve_tax_rate(
    session: AsyncSession,
    product: Product,
    *,
    territory: str = _DEFAULT_TERRITORY_CODE,
    at_date: date | None = None,
) -> TaxRate | None:
    """Resolve applicable tax rate for a product.

    Resolution order:
    1) Product.tax_rate_id
    2) Category.default_tax_rate_id
    3) Territory default tax code (TGC_NORMAL)
    """
    reference_date = at_date or date.today()
    product_tax_rate_id = getattr(product, "tax_rate_id", None)
    product_category_id = getattr(product, "category_id", None)

    if product_tax_rate_id is not None:
        try:
            product_rate = await session.get(TaxRate, product_tax_rate_id)
        except Exception:
            product_rate = None

        if _is_tax_rate_candidate_active(product_rate, at_date=reference_date):
            return product_rate

    if product_category_id is not None:
        try:
            category = await session.get(Category, product_category_id)
        except Exception:
            category = None

        if category is not None and category.default_tax_rate_id is not None:
            try:
                category_rate = await session.get(TaxRate, category.default_tax_rate_id)
            except Exception:
                category_rate = None

            if _is_tax_rate_candidate_active(category_rate, at_date=reference_date):
                return category_rate

    fallback_statement = (
        select(TaxRate)
        .where(
            TaxRate.code == _DEFAULT_TAX_CODE,
            TaxRate.territory_code == territory,
            col(TaxRate.is_active).is_(True),
            TaxRate.valid_from <= reference_date,
            (col(TaxRate.valid_until).is_(None) | (TaxRate.valid_until >= reference_date)),
        )
        .order_by(col(TaxRate.valid_from).desc())
        .limit(1)
    )
    try:
        fallback_result = await session.exec(fallback_statement)
        first_method = getattr(fallback_result, "first", None)
        if first_method is None or not callable(first_method):
            return None

        fallback_rate = first_method()
        if inspect.isawaitable(fallback_rate):
            fallback_rate = await fallback_rate
    except Exception:
        return None

    if _is_tax_rate_candidate_active(fallback_rate, at_date=reference_date):
        return fallback_rate
    return None


async def calculate_sale_price(
    session: AsyncSession,
    product: Product,
    *,
    group: PriceGroup | None = None,
    territory: str = _DEFAULT_TERRITORY_CODE,
) -> Decimal:
    """Calculate product sale price for a pricing group."""
    effective_group = group
    if effective_group is None:
        effective_group = await resolve_default_price_group(session)

    margin_rate_pct = _as_decimal(
        effective_group.margin_rate_pct if effective_group is not None else None,
        default=_DEFAULT_MARGIN_RATE_PCT,
    )
    cost_amount = _as_decimal(
        getattr(product, "cost_amount", None),
        default=_as_decimal(getattr(product, "base_price", None)),
    )
    customs_rate_pct = _as_decimal(getattr(product, "customs_rate_pct", None))

    tax_rate = await resolve_tax_rate(session, product, territory=territory)
    tax_rate_pct = _as_decimal(tax_rate.rate_pct if tax_rate is not None else None)

    sale_price = (
        cost_amount
        * (Decimal("1.00") + (customs_rate_pct / Decimal("100")))
        * (Decimal("1.00") + (margin_rate_pct / Decimal("100")))
        * (Decimal("1.00") + (tax_rate_pct / Decimal("100")))
    )

    return _quantize_money(sale_price)
