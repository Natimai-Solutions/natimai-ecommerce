"""
Supplier data normalization and validation helpers.

Used to sanitize supplier price/stock payloads before persisting products.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel

DECIMAL_PRECISION = Decimal("0.01")
DEFAULT_CURRENCY = "USD"
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def _to_decimal(value: Any, field_name: str) -> Decimal:
    """Execute to decimal."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must not be a boolean")

    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError) as exc:
        raise ValueError(f"{field_name} is not a valid decimal value") from exc

    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")

    return parsed.quantize(DECIMAL_PRECISION, rounding=ROUND_HALF_UP)


def normalize_supplier_price(
    value: Any,
    *,
    default: Decimal = Decimal("0.00"),
) -> Decimal:
    """Execute normalize supplier price."""
    if value is None or value == "":
        return default

    normalized = _to_decimal(value, "supplier_price")
    if normalized < 0:
        raise ValueError("supplier_price must be >= 0")
    return normalized


def normalize_supplier_quantity(
    value: Any,
    *,
    default: Decimal = Decimal("0.00"),
) -> Decimal:
    """Execute normalize supplier quantity."""
    if value is None or value == "":
        return default

    normalized = _to_decimal(value, "supplier_quantity")
    if normalized < 0:
        raise ValueError("supplier_quantity must be >= 0")
    return normalized


def normalize_supplier_currency(value: Any, *, default: str = DEFAULT_CURRENCY) -> str:
    """Execute normalize supplier currency."""
    if not isinstance(value, str):
        return default

    normalized = value.strip().upper()
    if not normalized:
        return default

    if not _CURRENCY_RE.fullmatch(normalized):
        return default

    return normalized


@dataclass(frozen=True)
class NormalizedSupplierSnapshot:
    """Represents normalized supplier snapshot."""

    supplier_price: Decimal
    base_price: Decimal
    supplier_quantity: Decimal
    supplier_price_currency: str


def normalize_supplier_snapshot(
    *,
    raw_price: Any,
    raw_quantity: Any,
    raw_currency: Any,
) -> NormalizedSupplierSnapshot:
    """Execute normalize supplier snapshot."""
    supplier_price = normalize_supplier_price(raw_price)
    supplier_quantity = normalize_supplier_quantity(raw_quantity)
    supplier_currency = normalize_supplier_currency(raw_currency)

    return NormalizedSupplierSnapshot(
        supplier_price=supplier_price,
        base_price=supplier_price,
        supplier_quantity=supplier_quantity,
        supplier_price_currency=supplier_currency,
    )


class ProductFilterRule(BaseModel):
    """Rule for filtering out non-product items (warranties, services, accessories).

    Fields:
    - ``supplier_subcategory`` / ``supplier_category``: exact match (case-insensitive)
    - ``name_keyword``: substring match in product name (case-insensitive)
    - ``unspsc_code``: exact match against UNSPSC codes found in technical_specifications

    Actions:
    - ``deactivate``: create/keep the product but set is_active=False
    - ``skip``: do not create the product at all (ignored at Level 2 — treated as deactivate)

    ``supplier``: when set, the rule only applies to that supplier name.
    """

    field: Literal["supplier_subcategory", "supplier_category", "name_keyword", "unspsc_code"]
    values: list[str]
    action: Literal["skip", "deactivate"] = "deactivate"
    supplier: str | None = None


def evaluate_product_filters(
    *,
    supplier_name: str,
    supplier_subcategory: str | None = None,
    supplier_category: str | None = None,
    name: str | None = None,
    unspsc_codes: list[str] | None = None,
    rules: list[ProductFilterRule],
) -> Literal["skip", "deactivate"] | None:
    """Evaluate filter rules against a product's attributes.

    Returns the most restrictive matching action, or None if no rule matches.
    ``skip`` takes precedence over ``deactivate``.
    """
    matched_action: Literal["skip", "deactivate"] | None = None

    for rule in rules:
        if rule.supplier is not None and rule.supplier != supplier_name:
            continue

        matched = False

        if rule.field == "supplier_subcategory" and supplier_subcategory:
            matched = any(v.casefold() == supplier_subcategory.casefold() for v in rule.values)
        elif rule.field == "supplier_category" and supplier_category:
            matched = any(v.casefold() == supplier_category.casefold() for v in rule.values)
        elif rule.field == "name_keyword" and name:
            name_lower = name.casefold()
            matched = any(v.casefold() in name_lower for v in rule.values)
        elif rule.field == "unspsc_code" and unspsc_codes:
            matched = any(v in unspsc_codes for v in rule.values)

        if matched:
            if rule.action == "skip":
                return "skip"
            matched_action = "deactivate"

    return matched_action


def meets_sync_thresholds(
    snapshot: NormalizedSupplierSnapshot,
    *,
    price_in_xpf: Decimal | None = None,
) -> bool:
    """Check whether a snapshot's price and quantity meet configured minimums.

    Only meaningful when called with real pricing data (i.e. from an inventory
    sync, not a catalog sync where price/quantity may be unavailable).

    ``price_in_xpf`` is the supplier price already converted to XPF. When
    provided, it is used for the price threshold comparison so that
    SUPPLIER_SYNC_MIN_PRICE is interpreted in XPF regardless of the
    supplier's invoice currency. When absent the raw ``supplier_price`` is
    used as a best-effort fallback (accurate only if currency is already XPF).
    """
    # Imported here to avoid circular dependency at module load time.
    from app.core.config import settings

    min_qty = settings.SUPPLIER_SYNC_MIN_QUANTITY
    min_price = settings.SUPPLIER_SYNC_MIN_PRICE
    if min_qty > 0 and snapshot.supplier_quantity < min_qty:
        return False
    if min_price > 0:
        comparable_price = (
            price_in_xpf if price_in_xpf is not None else snapshot.supplier_price
        )
        if comparable_price < min_price:
            return False
    return True
