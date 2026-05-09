from decimal import Decimal

import pytest

from app.utils.money import (
    decimal_to_minor_units,
    minor_units_to_decimal,
    parse_minor_units,
    quantize_amount,
)


def test_decimal_to_minor_units_eur() -> None:
    amount = Decimal("12.345")
    assert decimal_to_minor_units(amount, "EUR") == 1235


def test_decimal_to_minor_units_xpf() -> None:
    amount = Decimal("1234.6")
    assert decimal_to_minor_units(amount, "XPF") == 1235


def test_minor_units_to_decimal_by_currency_scale() -> None:
    assert minor_units_to_decimal(1235, "EUR") == Decimal("12.35")
    assert minor_units_to_decimal(1235, "XPF") == Decimal("1235")


def test_quantize_amount_uses_currency_scale() -> None:
    assert quantize_amount(Decimal("12.345"), "EUR") == Decimal("12.35")
    assert quantize_amount(Decimal("12.6"), "XPF") == Decimal("13")


@pytest.mark.parametrize("value", ["100", 100, Decimal("100")])
def test_parse_minor_units_accepts_integer_values(value: object) -> None:
    assert parse_minor_units(value) == 100


@pytest.mark.parametrize("value", ["10.5", -1, True, "abc"])
def test_parse_minor_units_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        parse_minor_units(value)
