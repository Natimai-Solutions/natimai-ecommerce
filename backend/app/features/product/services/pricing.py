from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.place.models import Place
from app.features.product.models.category import Category
from app.features.product.models.currency_rate import CurrencyRate
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import PricingMode, Product
from app.features.product.models.tax_rate import TaxRate
from app.features.product.services.pricing_parameters import (
    apply_fx_safety_margin,
    apply_payment_commission,
    load_pricing_parameters,
)
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.services.origin import (
    OriginContext,
    OriginRegime,
    load_origin_context,
    resolve_origin_regime,
    resolve_product_origin_regime,
)
from app.features.shipping.services.pricing import (
    _route_metadata_to_dict,
    resolve_billable_weight,
)

_MONEY_QUANT = Decimal("0.01")
_DEFAULT_MARGIN_RATE_PCT = Decimal("30.00")


def default_tax_code() -> str:
    """Rate applied when neither the product nor its category says otherwise."""
    return settings.DEFAULT_TAX_CODE


def default_territory_code() -> str:
    """Tax territory of the shop's own rates (``TERRITORY_PROFILE``)."""
    return settings.TAX_TERRITORY_CODE


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
    territory: str | None = None,
    at_date: date | None = None,
) -> TaxRate | None:
    """Resolve applicable tax rate for a product.

    Resolution order:
    1) Product.tax_rate_id
    2) Category.default_tax_rate_id
    3) Territory default tax code (``DEFAULT_TAX_CODE``: TGC_NORMAL, TVA_NORMALE…)
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
            TaxRate.code == default_tax_code(),
            TaxRate.territory_code == (territory or default_territory_code()),
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


def resolve_pricing_mode(product: Product) -> PricingMode:
    """Read the product's pricing mode, defaulting to the historical CAF mode.

    Read defensively (tests and admin previews hand in lightweight objects):
    an unknown or missing value is the import mode, never a cheaper one.
    """
    raw = getattr(product, "pricing_mode", None)
    if isinstance(raw, PricingMode):
        return raw
    try:
        return PricingMode(str(raw))
    except (TypeError, ValueError):
        return PricingMode.IMPORT


async def resolve_margin_rate_pct(
    session: AsyncSession,
    product: Product,
    *,
    group: PriceGroup | None,
) -> Decimal:
    """Resolve the margin applied to a product.

    Resolution order, mirroring the customs and tax rates:
    1) Product.margin_rate_pct (per-article override)
    2) Category.default_margin_rate_pct (the category is where a margin is
       normally decided)
    3) PriceGroup.margin_rate_pct (the customer's price group), else 30 %.
    """
    product_rate = getattr(product, "margin_rate_pct", None)
    if product_rate is not None:
        return _as_decimal(product_rate)

    category_id = getattr(product, "category_id", None)
    if category_id is not None:
        try:
            category = await session.get(Category, category_id)
        except Exception:
            category = None
        category_rate = getattr(category, "default_margin_rate_pct", None)
        if category_rate is not None:
            return _as_decimal(category_rate)

    return _as_decimal(
        group.margin_rate_pct if group is not None else None,
        default=_DEFAULT_MARGIN_RATE_PCT,
    )


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


async def resolve_effective_customs_rate_pct(
    session: AsyncSession,
    product: Product,
    *,
    origin_regime: OriginRegime | None = None,
) -> Decimal | None:
    """Customs rate actually applied to this product: 0 for a domestic origin.

    A supplier in the main warehouse's country (or a customs-free one) clears
    no border, whatever rate the product or its category carries for the
    import case. Otherwise the configured rate (None = unresolved) applies.
    """
    if not await product_applies_customs(session, product, origin_regime=origin_regime):
        return Decimal("0")
    return await resolve_customs_rate_pct(session, product)


async def product_applies_customs(
    session: AsyncSession,
    product: Product,
    *,
    origin_regime: OriginRegime | None = None,
    context: OriginContext | None = None,
) -> bool:
    """The one decision « does this product cross the customs border? ».

    Shared by the price, the publication gate, the order-line snapshot and
    the customs declaration fee, so they never disagree. ``fixed`` and
    ``domestic`` products never do (explicit product-level overrides); an
    ``import`` product follows the regime of its supplier place (UNKNOWN
    keeps the historical behaviour: customs apply).
    """
    if resolve_pricing_mode(product) is not PricingMode.IMPORT:
        return False
    regime = origin_regime
    if regime is None:
        regime = await resolve_product_origin_regime(session, product, context=context)
    return regime.applies_customs


async def calculate_sale_price(
    session: AsyncSession,
    product: Product,
    *,
    group: PriceGroup | None = None,
    territory: str | None = None,
    import_route: ShippingRoute | None = None,
    origin_regime: OriginRegime | None = None,
) -> Decimal:
    """Calculate the product sale price according to its ``pricing_mode``.

    ``fixed`` — ``base_price`` is the tax-inclusive price the admin typed;
    it is returned as is.

    ``domestic`` — the goods never cross the customs border (own warehouse,
    or a supplier of the same customs territory):
        sale_price = cost_in_reference × (1 + margin_rate_pct / 100)
                                       × (1 + tax_rate_pct / 100)

    ``import`` (default) — CAF customs base:
        insurance = (cost_in_reference + freight_variable) × insurance_rate
        caf       = cost_in_reference + freight_variable + insurance
        landed    = caf × (1 + customs_rate_pct / 100)
        sale_price = landed × (1 + margin_rate_pct / 100) × (1 + tax_rate_pct / 100)

    ``import_route``: the import leg (e.g. France → Papeete). When provided,
    its variable freight (price_per_kg × billable_weight) enters the CAF base.
    When None the freight component is zero (backward-compatible, useful for
    admin previews where no route has been chosen yet). Ignored outside the
    import mode.

    The margin resolves product → category → price group
    (:func:`resolve_margin_rate_pct`).

    ``origin_regime``: where the product comes from (see shipping/services/
    origin.py). A DOMESTIC origin — supplier in the main warehouse's country —
    crosses no border: no import freight, no insurance, no customs; the price
    is cost × margin × tax. Resolved from the product's supplier place when
    not given; UNKNOWN keeps the import formula (visible over-pricing beats
    silent under-pricing).

    Raises CurrencyRateMissing for unknown cost currencies.
    """
    mode = resolve_pricing_mode(product)
    if mode is PricingMode.FIXED:
        return _quantize_money(_as_decimal(getattr(product, "base_price", None)))

    # The origin place is the customs truth for the default (import) mode: a
    # supplier in the main warehouse's country prices as a domestic product.
    # ``domestic`` / ``fixed`` on the product are explicit overrides.
    regime = origin_regime
    if mode is PricingMode.IMPORT and regime is None:
        regime = await resolve_product_origin_regime(session, product)
    if regime is OriginRegime.DOMESTIC:
        mode = PricingMode.DOMESTIC

    effective_group = group
    if effective_group is None:
        effective_group = await resolve_default_price_group(session)

    margin_rate_pct = await resolve_margin_rate_pct(
        session, product, group=effective_group
    )
    # The payment commission grosses the final (tax-inclusive) price up so the
    # shop nets the price the formula computed (see pricing_parameters.py).
    parameters = await load_pricing_parameters(session)
    commission_pct = parameters.payment_commission_pct
    raw_cost = _as_decimal(
        getattr(product, "cost_amount", None),
        default=_as_decimal(getattr(product, "base_price", None)),
    )
    cost_currency = (
        getattr(product, "cost_currency", None) or settings.REFERENCE_CURRENCY
    )

    cost_in_reference, _fx_rate = await convert_to_reference_currency(
        session, raw_cost, cost_currency
    )
    # A cost quoted in a foreign currency carries an exchange risk until the
    # supplier is paid: the safety margin cushions it (pricing_parameters.py).
    cost_in_reference = apply_fx_safety_margin(
        cost_in_reference,
        parameters.fx_safety_margin_pct,
        converted=cost_currency != settings.REFERENCE_CURRENCY,
    )

    tax_rate = await resolve_tax_rate(session, product, territory=territory)
    tax_rate_pct = _as_decimal(tax_rate.rate_pct if tax_rate is not None else None)

    if mode is PricingMode.DOMESTIC:
        sale_price = (
            cost_in_reference
            * (Decimal("1.00") + (margin_rate_pct / Decimal("100")))
            * (Decimal("1.00") + (tax_rate_pct / Decimal("100")))
        )
        return apply_payment_commission(_quantize_money(sale_price), commission_pct)

    # None (neither product nor category rate) prices as 0 here, but such a
    # product is not publishable and cannot reach the cart — see
    # services/publication.py. Keeping this total avoids breaking admin
    # previews of products still being set up.
    customs_rate_pct = _as_decimal(
        await resolve_effective_customs_rate_pct(session, product, origin_regime=regime)
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

    # Insurance is priced on what is actually insured: the goods *and* the
    # freight paid to bring them here (ad valorem premiums are quoted on the
    # CIF/CAF value, not on the invoice value alone). Charging it on the cost
    # only under-recovers on exactly the items where the freight weighs most —
    # the heavy and the far-shipped. There is no circularity: the variable
    # freight is known before the customs base is assembled.
    insurance_rate = Decimal(str(settings.INSURANCE_RATE_PCT)) / Decimal("100")
    insurance = (cost_in_reference + freight_variable) * insurance_rate

    caf = cost_in_reference + freight_variable + insurance

    sale_price = (
        caf
        * (Decimal("1.00") + (customs_rate_pct / Decimal("100")))
        * (Decimal("1.00") + (margin_rate_pct / Decimal("100")))
        * (Decimal("1.00") + (tax_rate_pct / Decimal("100")))
    )

    return apply_payment_commission(_quantize_money(sale_price), commission_pct)


async def calculate_price_by_mode(
    session: AsyncSession,
    product: Product,
    import_routes: list[ShippingRoute],
    *,
    group: PriceGroup | None = None,
    territory: str | None = None,
) -> list[ShippingModePrice]:
    """Return a price breakdown for every import route.

    Each entry maps to one route (identified by ``service_level`` when set,
    otherwise by ``route_id``). The caller uses this list to build the
    ``shipping_modes`` payload returned in the product API response.
    The frontend can switch service levels locally without a refetch.

    Only products in the ``import`` pricing mode have an import leg: for the
    domestic and fixed modes the list is empty and the storefront shows the
    single ``base_price``.
    """
    results: list[ShippingModePrice] = []
    if resolve_pricing_mode(product) is not PricingMode.IMPORT:
        return results
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


# ---------------------------------------------------------------------------
# Bulk pricing: one load of the referentials, prices computed in memory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PlaceOrigin:
    """The two attributes :func:`resolve_origin_regime` reads on a place."""

    country: str | None
    customs_regime: str | None


@dataclass(frozen=True)
class _CategoryPricing:
    default_customs_rate_pct: Decimal | None
    default_margin_rate_pct: Decimal | None
    default_tax_rate_id: uuid.UUID | None


@dataclass
class PricingContext:
    """Referentials of :func:`calculate_sale_price` loaded once, prices in memory.

    ``calculate_sale_price`` resolves category, tax and currency with three to
    five queries per product; listing a few thousand products this way costs
    tens of thousands of queries. This context loads the price group, tax
    rates, currency rates and categories in four queries and reproduces the
    exact same resolution and formula without touching the database.

    Build one per request or per sync run (:meth:`for_session` caches it on
    the session for a minute). ``calculate_sale_price`` remains the reference
    for single products; parity is covered by an integration test.
    """

    group_margin_rate_pct: Decimal | None
    tax_rates_by_id: dict[uuid.UUID, TaxRate]
    default_tax_rate_pct: Decimal
    fx_rates: dict[str, Decimal]
    categories: dict[uuid.UUID, _CategoryPricing]
    insurance_rate_pct: Decimal
    reference_currency: str
    at_date: date
    #: Origin places (``country``, ``customs_regime``) and what they are
    #: compared against — the customs truth for import-mode products.
    places: dict[uuid.UUID, _PlaceOrigin] = field(default_factory=dict)
    main_warehouse: _PlaceOrigin | None = None
    free_countries: frozenset[str] = frozenset()
    #: Payment commission grossed into the price (pricing_parameters.py).
    payment_commission_pct: Decimal = Decimal("0")
    #: Cushion on costs converted from a foreign currency (same module).
    fx_safety_margin_pct: Decimal = Decimal("0")
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    #: How long :meth:`for_session` keeps reusing an instance.
    CACHE_TTL_SECONDS: ClassVar[int] = 60
    _SESSION_KEY: ClassVar[str] = "pricing_context"

    @classmethod
    async def load(
        cls,
        session: AsyncSession,
        *,
        group: PriceGroup | None = None,
        territory: str | None = None,
        at_date: date | None = None,
    ) -> PricingContext:
        """Load every referential the price formula reads."""
        reference_date: date = at_date if at_date is not None else date.today()

        effective_group = group
        if effective_group is None:
            effective_group = await resolve_default_price_group(session)
        group_margin = (
            _as_decimal(effective_group.margin_rate_pct)
            if effective_group is not None
            and getattr(effective_group, "margin_rate_pct", None) is not None
            else None
        )

        tax_rows = list((await session.exec(select(TaxRate))).all())
        tax_by_id = {row.id: row for row in tax_rows}
        default_candidates = sorted(
            (
                row
                for row in tax_rows
                if row.code == default_tax_code()
                and row.territory_code == (territory or default_territory_code())
                and _is_tax_rate_candidate_active(row, at_date=reference_date)
            ),
            key=lambda row: row.valid_from,
            reverse=True,
        )
        default_tax_pct = (
            _as_decimal(default_candidates[0].rate_pct)
            if default_candidates
            else Decimal("0")
        )

        fx_rows = list(
            (
                await session.exec(
                    select(CurrencyRate).where(
                        col(CurrencyRate.is_active).is_(True),
                        CurrencyRate.valid_from <= reference_date,
                        (
                            col(CurrencyRate.valid_until).is_(None)
                            | (col(CurrencyRate.valid_until) >= reference_date)
                        ),
                    )
                )
            ).all()
        )
        fx: dict[str, Decimal] = {}
        fx_from: dict[str, date] = {}
        for row in fx_rows:
            previous = fx_from.get(row.currency_code)
            if previous is None or row.valid_from > previous:
                fx[row.currency_code] = _as_decimal(row.rate_to_reference)
                fx_from[row.currency_code] = row.valid_from

        category_rows = list((await session.exec(select(Category))).all())
        categories = {
            row.id: _CategoryPricing(
                default_customs_rate_pct=(
                    _as_decimal(row.default_customs_rate_pct)
                    if row.default_customs_rate_pct is not None
                    else None
                ),
                default_margin_rate_pct=(
                    _as_decimal(row.default_margin_rate_pct)
                    if row.default_margin_rate_pct is not None
                    else None
                ),
                default_tax_rate_id=row.default_tax_rate_id,
            )
            for row in category_rows
        }

        parameters = await load_pricing_parameters(session)
        origin = await load_origin_context(session)
        place_rows = list(
            (
                await session.exec(
                    select(col(Place.id), col(Place.country), col(Place.customs_regime))
                )
            ).all()
        )
        places = {
            row[0]: _PlaceOrigin(country=row[1], customs_regime=row[2])
            for row in place_rows
        }
        main_warehouse = (
            _PlaceOrigin(
                country=origin.main_warehouse.country,
                customs_regime=origin.main_warehouse.customs_regime,
            )
            if origin.main_warehouse is not None
            else None
        )

        return cls(
            group_margin_rate_pct=group_margin,
            tax_rates_by_id=tax_by_id,
            default_tax_rate_pct=default_tax_pct,
            fx_rates=fx,
            categories=categories,
            insurance_rate_pct=Decimal(str(settings.INSURANCE_RATE_PCT)),
            reference_currency=settings.REFERENCE_CURRENCY,
            at_date=reference_date,
            places=places,
            main_warehouse=main_warehouse,
            free_countries=origin.free_countries,
            payment_commission_pct=parameters.payment_commission_pct,
            fx_safety_margin_pct=parameters.fx_safety_margin_pct,
        )

    @classmethod
    async def for_session(cls, session: AsyncSession) -> PricingContext:
        """Context cached on the session (``Session.info``) for a short while.

        A sync run updating thousands of products shares one load; an admin
        change to a rate is picked up within :attr:`CACHE_TTL_SECONDS`, and
        the refresh task rebuilds its own context anyway.
        """
        info = getattr(session, "info", None)
        if isinstance(info, dict):
            cached = info.get(cls._SESSION_KEY)
            if isinstance(cached, PricingContext) and (
                datetime.now(timezone.utc) - cached.loaded_at
            ) < timedelta(seconds=cls.CACHE_TTL_SECONDS):
                return cached
        context = await cls.load(session)
        if isinstance(info, dict):
            info[cls._SESSION_KEY] = context
        return context

    # -- resolution -------------------------------------------------------

    def _category(self, product: Product) -> _CategoryPricing | None:
        category_id = getattr(product, "category_id", None)
        if category_id is None:
            return None
        return self.categories.get(category_id)

    def margin_rate_pct(self, product: Product) -> Decimal:
        """Product → category → price group → 30 %."""
        own = getattr(product, "margin_rate_pct", None)
        if own is not None:
            return _as_decimal(own)
        category = self._category(product)
        if category is not None and category.default_margin_rate_pct is not None:
            return category.default_margin_rate_pct
        if self.group_margin_rate_pct is not None:
            return self.group_margin_rate_pct
        return _DEFAULT_MARGIN_RATE_PCT

    def customs_rate_pct(self, product: Product) -> Decimal | None:
        """Product → category; ``None`` when neither is set (unpublishable)."""
        own = getattr(product, "customs_rate_pct", None)
        if own is not None:
            return _as_decimal(own)
        category = self._category(product)
        if category is None:
            return None
        return category.default_customs_rate_pct

    def tax_rate_pct(self, product: Product) -> Decimal:
        """Product tax rate → category default → territory default."""
        own_id = getattr(product, "tax_rate_id", None)
        if own_id is not None:
            rate = self.tax_rates_by_id.get(own_id)
            if _is_tax_rate_candidate_active(rate, at_date=self.at_date):
                return _as_decimal(rate.rate_pct)  # type: ignore[union-attr]
        category = self._category(product)
        if category is not None and category.default_tax_rate_id is not None:
            rate = self.tax_rates_by_id.get(category.default_tax_rate_id)
            if _is_tax_rate_candidate_active(rate, at_date=self.at_date):
                return _as_decimal(rate.rate_pct)  # type: ignore[union-attr]
        return self.default_tax_rate_pct

    def origin_regime(self, product: Product) -> OriginRegime:
        """Regime of the product's supplier place, like
        :func:`resolve_product_origin_regime` but in memory."""
        origin_id = getattr(product, "supplier_place_id", None)
        if origin_id is None:
            return OriginRegime.UNKNOWN
        origin = self.places.get(origin_id)
        if origin is None:
            return OriginRegime.UNKNOWN
        return resolve_origin_regime(
            origin,  # type: ignore[arg-type]
            self.main_warehouse,  # type: ignore[arg-type]
            free_countries=self.free_countries,
        )

    def effective_mode(self, product: Product) -> PricingMode:
        """``pricing_mode`` with the origin applied: an import-mode product
        from a domestic place prices as ``domestic`` (see
        :func:`calculate_sale_price`)."""
        mode = resolve_pricing_mode(product)
        if (
            mode is PricingMode.IMPORT
            and self.origin_regime(product) is OriginRegime.DOMESTIC
        ):
            return PricingMode.DOMESTIC
        return mode

    def applies_customs(self, product: Product) -> bool:
        """In-memory twin of :func:`product_applies_customs`."""
        if resolve_pricing_mode(product) is not PricingMode.IMPORT:
            return False
        return self.origin_regime(product).applies_customs

    def to_reference(self, amount: Decimal, currency: str) -> Decimal:
        """Convert to the reference currency; raises CurrencyRateMissing."""
        if currency == self.reference_currency:
            return amount
        rate = self.fx_rates.get(currency)
        if rate is None:
            raise CurrencyRateMissing(currency)
        return _quantize_money(amount * rate)

    def price(
        self, product: Product, *, import_route: ShippingRoute | None = None
    ) -> Decimal:
        """Same formula as :func:`calculate_sale_price`, no database access."""
        mode = self.effective_mode(product)
        if mode is PricingMode.FIXED:
            return _quantize_money(_as_decimal(getattr(product, "base_price", None)))

        margin = self.margin_rate_pct(product)
        raw_cost = _as_decimal(
            getattr(product, "cost_amount", None),
            default=_as_decimal(getattr(product, "base_price", None)),
        )
        currency = getattr(product, "cost_currency", None) or self.reference_currency
        cost = apply_fx_safety_margin(
            self.to_reference(raw_cost, currency),
            self.fx_safety_margin_pct,
            converted=currency != self.reference_currency,
        )
        tax = self.tax_rate_pct(product)

        if mode is PricingMode.DOMESTIC:
            return apply_payment_commission(
                _quantize_money(
                    cost
                    * (Decimal("1.00") + margin / Decimal("100"))
                    * (Decimal("1.00") + tax / Decimal("100"))
                ),
                self.payment_commission_pct,
            )

        customs = _as_decimal(self.customs_rate_pct(product))
        freight = Decimal("0")
        if import_route is not None:
            weight_kg = _as_decimal(getattr(product, "weight", None))
            volume_m3 = _compute_volume_m3(product)
            billable = resolve_billable_weight(
                weight_kg,
                volume_m3,
                metadata=_route_metadata_to_dict(import_route),
                mode=getattr(import_route, "mode", None),
            )
            freight = _as_decimal(import_route.price_per_kg) * billable
        insurance = (cost + freight) * (self.insurance_rate_pct / Decimal("100"))
        caf = cost + freight + insurance
        return apply_payment_commission(
            _quantize_money(
                caf
                * (Decimal("1.00") + customs / Decimal("100"))
                * (Decimal("1.00") + margin / Decimal("100"))
                * (Decimal("1.00") + tax / Decimal("100"))
            ),
            self.payment_commission_pct,
        )
