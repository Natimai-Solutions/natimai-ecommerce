from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

DEFAULT_CURRENCY_DECIMALS = 2
ZERO_DECIMAL_CURRENCIES = {"XPF", "JPY", "KRW"}


def currency_decimals(currency: str | None) -> int:
    normalized = (currency or "").strip().upper()
    if normalized in ZERO_DECIMAL_CURRENCIES:
        return 0
    return DEFAULT_CURRENCY_DECIMALS


def quantize_amount(amount: Decimal, currency: str | None = None) -> Decimal:
    decimals = currency_decimals(currency)
    exponent = Decimal("1").scaleb(-decimals)
    return amount.quantize(exponent, rounding=ROUND_HALF_UP)


def decimal_to_minor_units(amount: Decimal, currency: str | None = None) -> int:
    normalized = quantize_amount(amount, currency)
    factor = Decimal(10) ** currency_decimals(currency)
    return int((normalized * factor).to_integral_value(rounding=ROUND_HALF_UP))


def minor_units_to_decimal(amount_minor: int, currency: str | None = None) -> Decimal:
    if isinstance(amount_minor, bool):
        raise ValueError("amount_minor must not be a boolean")

    factor = Decimal(10) ** currency_decimals(currency)
    amount = Decimal(amount_minor) / factor
    return quantize_amount(amount, currency)


def parse_minor_units(value: Any) -> int:
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
