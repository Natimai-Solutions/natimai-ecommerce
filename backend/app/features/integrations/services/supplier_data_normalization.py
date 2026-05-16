"""
Supplier data normalization and validation helpers.

Used to sanitize supplier price/stock payloads before persisting products.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

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
