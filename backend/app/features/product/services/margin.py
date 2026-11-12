"""Margin of a sale: price excl. tax − payment commission − cost price.

* ``unit_cost`` — the cost price excl. tax in the reference currency: the
  purchase cost converted (no FX safety cushion: that is a pricing reserve, not
  a cost), plus insurance and customs for an import-mode product (no import
  leg, like the list price). Unknown (None) when no purchase cost is entered.
* ``margin_amount`` — price excl. tax − commission − unit cost, per unit.
* ``margin_pct`` — share of the price excl. tax (taux de marque).
* ``markup_pct`` — share of the cost (taux de marge).

Prices are stored tax included: the price excl. tax is ``price / (1 + tax)``.
The payment commission (pricing_parameters) is taken on what the customer
pays, so it is a cost of the sale.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.config import settings
from app.utils.money import quantize_amount, split_incl_tax

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")


def _pct(value: Decimal) -> Decimal:
    """A percentage, to the hundredth."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    """An amount in the reference currency (whole francs in XPF): the margin
    rounded to the cent whatever the currency (audit 2026-11)."""
    return quantize_amount(value, settings.REFERENCE_CURRENCY)


@dataclass(frozen=True)
class MarginFigures:
    price_incl_tax: Decimal
    tax_rate_pct: Decimal
    price_excl_tax: Decimal
    tax_amount: Decimal
    commission_amount: Decimal
    unit_cost: Decimal
    margin_amount: Decimal
    #: Margin / price excl. tax (taux de marque); None for a zero price.
    margin_pct: Decimal | None
    #: Margin / cost (taux de marge); None for a zero cost.
    markup_pct: Decimal | None


def compute_margin(
    *,
    price_incl_tax: Decimal | None,
    tax_rate_pct: Decimal | None,
    unit_cost: Decimal | None,
    commission_pct: Decimal | None = None,
) -> MarginFigures | None:
    """The margin figures of one unit, None when the cost or price is unknown."""
    if unit_cost is None or price_incl_tax is None:
        return None
    price = Decimal(price_incl_tax)
    tax = Decimal(tax_rate_pct or 0)
    cost = Decimal(unit_cost)
    commission = Decimal(commission_pct or 0)
    excl = (
        split_incl_tax(price, tax, settings.REFERENCE_CURRENCY)[0]
        if price
        else Decimal("0")
    )
    commission_amount = _money(price * commission / _HUNDRED)
    margin = _money(excl - commission_amount - cost)
    return MarginFigures(
        price_incl_tax=_money(price),
        tax_rate_pct=tax,
        price_excl_tax=excl,
        tax_amount=_money(price - excl),
        commission_amount=commission_amount,
        unit_cost=_money(cost),
        margin_amount=margin,
        margin_pct=_pct(margin / excl * _HUNDRED) if excl > 0 else None,
        markup_pct=_pct(margin / cost * _HUNDRED) if cost > 0 else None,
    )


def line_unit_cost(line: Any) -> Decimal | None:
    """Cost price of one unit of an order line.

    The snapshot taken at checkout; for lines older than it, the purchase
    cost converted with the rate of the day (customs and insurance unknown).
    """
    snapshot = getattr(line, "unit_cost_snapshot", None)
    if snapshot is not None:
        return Decimal(snapshot)
    cost = getattr(line, "cost_amount_snapshot", None)
    if cost is None or Decimal(cost) <= 0:
        return None
    currency = getattr(line, "cost_currency_snapshot", None)
    rate = getattr(line, "fx_rate_used", None)
    if currency and currency != settings.REFERENCE_CURRENCY:
        if rate is None:
            return None
        return _money(Decimal(cost) * Decimal(rate))
    return _money(Decimal(cost))


__all__ = ["MarginFigures", "compute_margin", "line_unit_cost"]
