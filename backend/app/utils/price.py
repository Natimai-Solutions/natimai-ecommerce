def price_ht(prix_ttc: float, tax_rate: float) -> float:
    return round(prix_ttc / (1 + tax_rate), 2)


def price_ttc(price_ht: float, tax_rate: float) -> float:
    return round(price_ht * (1 + tax_rate), 2)


def round_price(price: float, precision: int = 2) -> float:
    """Round the price to the specified precision."""
    return round(price, precision)