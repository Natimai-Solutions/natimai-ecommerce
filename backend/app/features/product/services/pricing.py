from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.product.models.category import Category
from app.features.product.models.currency_rate import CurrencyRate
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import Product
from app.features.product.models.tax_rate import TaxRate
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.services.pricing import (
    _route_metadata_to_dict,
    resolve_billable_weight,
)

_MONEY_QUANT = Decimal("0.01")
_DEFAULT_MARGIN_RATE_PCT = Decimal("30.00")
_DEFAULT_TAX_CODE = "TGC_NORMAL"
_DEFAULT_TERRITORY_CODE = "PF"


@dataclass(frozen=True)
class ShippingModePrice:
    """Price breakdown for one import service level (used by calculate_price_by_mode)."""

    route_id: str
    service_level: str | None
    customer_label: str | None
    freight: Decimal
    sale_price: Decimal
    eta_days: int | None
    carbon_footprint_kg_co2e: float | None


class CurrencyRateMissing(Exception):
    """Raised when no active CurrencyRate exists for a given currency."""

    def __init__(self, currency_code: str) -> None:
        self.currency_code = currency_code
        super().__init__(
            f"No active CurrencyRate found for '{currency_code}'. "
            "Create one via PUT /admin/currency-rates/{code} before syncing products in this currency."
        )


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


async def convert_to_reference_currency(
    session: AsyncSession,
    amount: Decimal,
    from_currency: str,
    *,
    at_date: date | None = None,
) -> tuple[Decimal, Decimal]:
    """Convert an amount from `from_currency` to the reference currency.

    Returns (amount_in_reference, rate_used).
    When from_currency is already the reference currency, returns (amount, Decimal("1")).
    Raises CurrencyRateMissing if no active rate is found.
    """
    if from_currency == settings.REFERENCE_CURRENCY:
        return amount, Decimal("1")

    reference_date: date = at_date if at_date is not None else date.today()
    statement = (
        select(CurrencyRate)
        .where(
            CurrencyRate.currency_code == from_currency,
            col(CurrencyRate.is_active).is_(True),
            CurrencyRate.valid_from <= reference_date,
            (
                col(CurrencyRate.valid_until).is_(None)
                | (col(CurrencyRate.valid_until) >= reference_date)
            ),
        )
        .order_by(col(CurrencyRate.valid_from).desc())
        .limit(1)
    )
    result = await session.exec(statement)
    rate = result.first()
    if rate is None:
        raise CurrencyRateMissing(from_currency)

    return _quantize_money(amount * rate.rate_to_reference), rate.rate_to_reference


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
    reference_date: date = at_date if at_date is not None else date.today()
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
            (
                col(TaxRate.valid_until).is_(None)
                | (col(TaxRate.valid_until) >= reference_date)
            ),
        )
        .order_by(col(TaxRate.valid_from).desc())
        .limit(1)
    )
    try:
        fallback_result = await session.exec(fallback_statement)
        first_method = getattr(fallback_result, "first", None)
        if first_method is None or not callable(first_method):
            return None

        raw = first_method()
        if inspect.isawaitable(raw):
            raw = await raw
        fallback_rate: TaxRate | None = raw
    except Exception:
        return None

    if _is_tax_rate_candidate_active(fallback_rate, at_date=reference_date):
        return fallback_rate
    return None


async def resolve_customs_rate_pct(
    session: AsyncSession,
    product: Product,
) -> Decimal | None:
    """Resolve the applicable customs rate for a product.

    Resolution order, mirroring resolve_tax_rate:
    1) Product.customs_rate_pct
    2) Category.default_customs_rate_pct

    Returns None when neither is set. Callers must treat None as "unknown",
    never as zero: the supplier sync never fills this rate, so a silent zero
    would under-price every synced product by the whole customs bracket.
    Publication is gated on this resolving (see services/publication.py).
    """
    product_rate = getattr(product, "customs_rate_pct", None)
    if product_rate is not None:
        return _as_decimal(product_rate)

    category_id = getattr(product, "category_id", None)
    if category_id is None:
        return None

    try:
        category = await session.get(Category, category_id)
    except Exception:
        return None

    if category is None:
        return None

    category_rate = getattr(category, "default_customs_rate_pct", None)
    if category_rate is None:
        return None
    return _as_decimal(category_rate)


def _compute_volume_m3(product: Product) -> Decimal | None:
    """Return product volume in m³ from dimensions in cm, or None if any dim is missing."""
    length = getattr(product, "dimensions_length", None)
    width = getattr(product, "dimensions_width", None)
    height = getattr(product, "dimensions_height", None)
    if any(v is None for v in (length, width, height)):
        return None
    try:
        return (
            Decimal(str(length))
            * Decimal(str(width))
            * Decimal(str(height))
            / Decimal("1000000")
        )
    except Exception:
        return None


async def calculate_sale_price(
    session: AsyncSession,
    product: Product,
    *,
    group: PriceGroup | None = None,
    territory: str = _DEFAULT_TERRITORY_CODE,
    import_route: ShippingRoute | None = None,
) -> Decimal:
    """Calculate product sale price using the CAF customs base.

    Formula:
        caf       = cost_in_reference + freight_variable + insurance
        landed    = caf × (1 + customs_rate_pct / 100)
        sale_price = landed × (1 + margin_rate_pct / 100) × (1 + tax_rate_pct / 100)

    ``import_route``: the import leg (e.g. France → Papeete). When provided,
    its variable freight (price_per_kg × billable_weight) enters the CAF base.
    When None the freight component is zero (backward-compatible, useful for
    admin previews where no route has been chosen yet).

    Raises CurrencyRateMissing for unknown cost currencies.
    """
    effective_group = group
    if effective_group is None:
        effective_group = await resolve_default_price_group(session)

    margin_rate_pct = _as_decimal(
        effective_group.margin_rate_pct if effective_group is not None else None,
        default=_DEFAULT_MARGIN_RATE_PCT,
    )
    raw_cost = _as_decimal(
        getattr(product, "cost_amount", None),
        default=_as_decimal(getattr(product, "base_price", None)),
    )
    cost_currency = (
        getattr(product, "cost_currency", None) or settings.REFERENCE_CURRENCY
    )
    # None (neither product nor category rate) prices as 0 here, but such a
    # product is not publishable and cannot reach the cart — see
    # services/publication.py. Keeping this total avoids breaking admin
    # previews of products still being set up.
    customs_rate_pct = _as_decimal(await resolve_customs_rate_pct(session, product))

    cost_in_reference, _fx_rate = await convert_to_reference_currency(
        session, raw_cost, cost_currency
    )

    # Variable freight from import route (price_per_kg × billable_weight).
    # The fixed base_price/handling fee is NOT included here: it belongs to
    # the shipment level (per-order), not the unit price.
    freight_variable = Decimal("0")
    if import_route is not None:
        weight_kg = _as_decimal(getattr(product, "weight", None))
        volume_m3 = _compute_volume_m3(product)
        route_meta = _route_metadata_to_dict(import_route)
        billable_weight_kg = resolve_billable_weight(
            weight_kg,
            volume_m3,
            metadata=route_meta,
            mode=getattr(import_route, "mode", None),
        )
        freight_variable = _as_decimal(import_route.price_per_kg) * billable_weight_kg

    # Insurance on cost only (not on freight, to avoid circularity).
    insurance_rate = Decimal(str(settings.INSURANCE_RATE_PCT)) / Decimal("100")
    insurance = cost_in_reference * insurance_rate

    caf = cost_in_reference + freight_variable + insurance

    tax_rate = await resolve_tax_rate(session, product, territory=territory)
    tax_rate_pct = _as_decimal(tax_rate.rate_pct if tax_rate is not None else None)

    sale_price = (
        caf
        * (Decimal("1.00") + (customs_rate_pct / Decimal("100")))
        * (Decimal("1.00") + (margin_rate_pct / Decimal("100")))
        * (Decimal("1.00") + (tax_rate_pct / Decimal("100")))
    )

    return _quantize_money(sale_price)


async def calculate_price_by_mode(
    session: AsyncSession,
    product: Product,
    import_routes: list[ShippingRoute],
    *,
    group: PriceGroup | None = None,
    territory: str = _DEFAULT_TERRITORY_CODE,
) -> list[ShippingModePrice]:
    """Return a price breakdown for every import route.

    Each entry maps to one route (identified by ``service_level`` when set,
    otherwise by ``route_id``). The caller uses this list to build the
    ``shipping_modes`` payload returned in the product API response.
    The frontend can switch service levels locally without a refetch.
    """
    results: list[ShippingModePrice] = []
    for route in import_routes:
        weight_kg = _as_decimal(getattr(product, "weight", None))
        volume_m3 = _compute_volume_m3(product)
        route_meta = _route_metadata_to_dict(route)
        billable_weight_kg = resolve_billable_weight(
            weight_kg,
            volume_m3,
            metadata=route_meta,
            mode=getattr(route, "mode", None),
        )
        freight = _quantize_money(_as_decimal(route.price_per_kg) * billable_weight_kg)
        sale_price = await calculate_sale_price(
            session,
            product,
            group=group,
            territory=territory,
            import_route=route,
        )
        results.append(
            ShippingModePrice(
                route_id=str(route.id),
                service_level=getattr(route, "service_level", None),
                customer_label=getattr(route, "customer_label", None),
                freight=freight,
                sale_price=sale_price,
                eta_days=getattr(route, "eta_days", None),
                carbon_footprint_kg_co2e=getattr(
                    route, "carbon_footprint_kg_co2e", None
                ),
            )
        )
    return results
