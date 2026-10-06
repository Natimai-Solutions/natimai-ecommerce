"""Currencies a payment method can collect in.

The order is priced and billed in the shop's reference currency; the visitor's
display currency only changes what is shown. A method lists the currencies it
can collect in (empty = any): the checkout tells a customer whose display
currency is not the one charged that the payment is made in another currency,
with the converted amount, so nobody is surprised by the amount on their
statement.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import reference_currency
from app.features.payment.models.payment_method import PaymentMethod
from app.features.product.models.currency_rate import CurrencyRate

_ISO_CODE = re.compile(r"^[A-Z]{3}$")


def normalize_currencies(values: list[str]) -> list[str]:
    """Upper-cased, trimmed, deduplicated ISO 4217 codes; ``ValueError`` when
    an entry is not three letters."""
    out: list[str] = []
    for raw in values:
        code = (raw or "").strip().upper()
        if not code:
            continue
        if not _ISO_CODE.match(code):
            raise ValueError(f"« {raw} » n'est pas un code devise ISO (trois lettres)")
        if code not in out:
            out.append(code)
    return out


def charge_currency_for(
    method: PaymentMethod, order_currency: str | None = None
) -> str:
    """The currency a payment with ``method`` is made in.

    The order currency (the reference) when the method accepts it or lists
    nothing; else the first currency the method lists (a wallet that only
    settles in EUR, for instance).
    """
    base = order_currency or reference_currency()
    accepted = [c.upper() for c in (method.currencies or [])]
    if not accepted or base.upper() in accepted:
        return base.upper()
    return accepted[0]


def accepts_currency(method: PaymentMethod, currency: str | None) -> bool:
    """Whether the method lists ``currency`` (or lists nothing at all)."""
    accepted = [c.upper() for c in (method.currencies or [])]
    return not accepted or (currency or "").upper() in accepted


async def rate_from_reference(
    session: AsyncSession, currency: str, *, at_date: date | None = None
) -> Decimal | None:
    """``rate_to_reference`` of ``currency`` (1 unit = this many reference
    units): ``1`` for the reference itself, ``None`` when no active rate
    exists. An amount in the reference currency divided by it is the amount
    in ``currency``."""
    if currency.upper() == reference_currency().upper():
        return Decimal("1")
    today = at_date or date.today()
    rate = (
        await session.exec(
            select(CurrencyRate)
            .where(
                col(CurrencyRate.currency_code) == currency.upper(),
                col(CurrencyRate.is_active).is_(True),
                col(CurrencyRate.valid_from) <= today,
                (
                    col(CurrencyRate.valid_until).is_(None)
                    | (col(CurrencyRate.valid_until) >= today)
                ),
            )
            .order_by(col(CurrencyRate.valid_from).desc())
            .limit(1)
        )
    ).first()
    return rate.rate_to_reference if rate is not None else None


__all__ = [
    "accepts_currency",
    "charge_currency_for",
    "normalize_currencies",
    "rate_from_reference",
]
