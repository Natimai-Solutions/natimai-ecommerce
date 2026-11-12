from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

DEFAULT_CURRENCY_DECIMALS = 2
ZERO_DECIMAL_CURRENCIES = {"XPF", "JPY", "KRW"}


def currency_decimals(currency: str | None) -> int:
    """Execute currency decimals."""
    normalized = (currency or "").strip().upper()
    if normalized in ZERO_DECIMAL_CURRENCIES:
        return 0
    return DEFAULT_CURRENCY_DECIMALS


def quantize_amount(amount: Decimal, currency: str | None = None) -> Decimal:
    """Execute quantize amount."""
    decimals = currency_decimals(currency)
    exponent = Decimal("1").scaleb(-decimals)
    return amount.quantize(exponent, rounding=ROUND_HALF_UP)


def reference_price(amount: Decimal) -> Decimal:
    """A price shown or billed to a customer, in the reference currency:
    rounded to that currency's unit (whole francs in XPF, cents in EUR).

    The sale price used to be rounded to the cent whatever the currency:
    11 600,37 F shown 11 600 F, two of them billed 23 201 F (audit 2026-11).
    Intermediate amounts (converted cost, freight…) keep their precision;
    only the price itself is rounded, once.
    """
    from app.core.config import settings

    return quantize_amount(Decimal(amount), settings.REFERENCE_CURRENCY)


def split_incl_tax(
    amount_incl: Decimal, rate_pct: Decimal, currency: str | None
) -> tuple[Decimal, Decimal]:
    """Split a tax-inclusive amount into ``(excl_tax, tax)`` in ``currency``.

    The one rule of the invoice, the credit note and the margin (they each
    had their own): the amount excl. tax is ``incl / (1 + rate)`` rounded to
    the currency's unit, the tax is the remainder, so ``excl + tax == incl``.
    """
    incl = Decimal(amount_incl)
    divisor = Decimal("1") + (Decimal(rate_pct or 0) / Decimal("100"))
    excl = quantize_amount(incl / divisor, currency)
    return excl, incl - excl


def decimal_to_minor_units(amount: Decimal, currency: str | None = None) -> int:
    """Execute decimal to minor units."""
    normalized = quantize_amount(amount, currency)
    factor = Decimal(10) ** currency_decimals(currency)
    return int((normalized * factor).to_integral_value(rounding=ROUND_HALF_UP))


def minor_units_to_decimal(amount_minor: int, currency: str | None = None) -> Decimal:
    """Execute minor units to decimal."""
    if isinstance(amount_minor, bool):
        raise ValueError("amount_minor must not be a boolean")

    factor = Decimal(10) ** currency_decimals(currency)
    amount = Decimal(amount_minor) / factor
    return quantize_amount(amount, currency)


def parse_minor_units(value: Any) -> int:
    """Parse minor units."""
    if isinstance(value, bool):
        raise ValueError("amount must not be a boolean")

    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError) as exc:
        raise ValueError("amount is not a valid number") from exc

    if not parsed.is_finite():
        raise ValueError("amount must be finite")

    if parsed != parsed.to_integral_value():
        raise ValueError("amount must be expressed in minor units (integer)")

    amount_minor = int(parsed)
    if amount_minor < 0:
        raise ValueError("amount must be >= 0")

    return amount_minor
