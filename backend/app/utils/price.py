from decimal import Decimal


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    """Execute to decimal."""
    return Decimal(str(value).strip())


def price_ht(
    prix_ttc: Decimal | int | float | str, tax_rate: Decimal | int | float | str
) -> Decimal:
    """Execute price ht."""
    gross = _to_decimal(prix_ttc)
    rate = _to_decimal(tax_rate)
    return round_price(gross / (Decimal("1") + rate), precision=2)


def price_ttc(
    price_ht: Decimal | int | float | str, tax_rate: Decimal | int | float | str
) -> Decimal:
    """Execute price ttc."""
    net = _to_decimal(price_ht)
    rate = _to_decimal(tax_rate)
    return round_price(net * (Decimal("1") + rate), precision=2)


def round_price(price: Decimal | int | float | str, precision: int = 2) -> Decimal:
    """Round the price to the specified precision."""
    value = _to_decimal(price)
    exponent = Decimal("1").scaleb(-precision)
    return value.quantize(exponent)
