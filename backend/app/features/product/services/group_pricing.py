"""What a customer pays: the reference price, adjusted for their group.

The pricing formula (pricing.py) gives the **reference price** of an article
(the default group's: Particulier), materialized in ``sale_price_cached``.
A customer of another group pays:

1. the price typed for their group on the article
   (:class:`ProductGroupPrice`), when there is one;
2. otherwise the reference price less their group's discount
   (``PriceGroup.discount_pct``) — on every article, computed or fixed.

A visitor who is not signed in, or a customer without a group, is priced as
the default group. Search filters and sorts stay on the reference price.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product_group_price import ProductGroupPrice
from app.features.user.models.user import User

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")


def apply_discount(reference: Decimal, discount_pct: Decimal | None) -> Decimal:
    """Reference price less a group discount, to the cent."""
    if not discount_pct or reference <= 0:
        return reference
    return (reference * (_HUNDRED - Decimal(discount_pct)) / _HUNDRED).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )


@dataclass(frozen=True)
class GroupPricing:
    """One group's discount and the prices typed for it, for a set of articles."""

    group_id: uuid.UUID | None
    discount_pct: Decimal = Decimal("0")
    prices: dict[uuid.UUID, Decimal] = field(default_factory=dict)

    @property
    def neutral(self) -> bool:
        return not self.discount_pct and not self.prices

    def price(self, product_id: uuid.UUID, reference: Decimal) -> Decimal:
        typed = self.prices.get(product_id)
        if typed is not None:
            return typed
        return apply_discount(reference, self.discount_pct)


async def _user_group_id(session: AsyncSession, user: Any | None) -> uuid.UUID | None:
    """The user's group id, without lazy-loading an expired ORM instance.

    Routes often commit before pricing (the cart does): the signed-in user is
    then expired, and reading an attribute would reload it synchronously —
    impossible under asyncio. The id is read from the identity instead.
    """
    if user is None:
        return None
    state = sa_inspect(user, raiseerr=False)
    if state is None or "price_group_id" not in state.unloaded:
        return getattr(user, "price_group_id", None)
    identity = state.identity
    if not identity:
        return None
    return (
        await session.exec(
            select(User.price_group_id).where(col(User.id) == identity[0])
        )
    ).first()


async def resolve_customer_group(
    session: AsyncSession, user: Any | None
) -> PriceGroup | None:
    """The customer's group, or the default group (visitor, no group)."""
    group_id = await _user_group_id(session, user)
    if group_id is not None:
        group = await session.get(PriceGroup, group_id)
        if group is not None and group.is_active:
            return group
    return (
        await session.exec(
            select(PriceGroup).where(
                col(PriceGroup.default).is_(True), col(PriceGroup.is_active).is_(True)
            )
        )
    ).first()


async def load_group_pricing(
    session: AsyncSession,
    group: PriceGroup | None,
    product_ids: Iterable[uuid.UUID],
) -> GroupPricing:
    """The group's discount and its typed prices for ``product_ids``."""
    if group is None:
        return GroupPricing(group_id=None)
    ids = list({pid for pid in product_ids if pid is not None})
    prices: dict[uuid.UUID, Decimal] = {}
    if ids:
        rows = await session.exec(
            select(ProductGroupPrice).where(
                col(ProductGroupPrice.price_group_id) == group.id,
                col(ProductGroupPrice.product_id).in_(ids),
            )
        )
        prices = {row.product_id: Decimal(row.price) for row in rows.all()}
    return GroupPricing(
        group_id=group.id,
        discount_pct=Decimal(group.discount_pct or 0),
        prices=prices,
    )


async def pricing_for_user(
    session: AsyncSession, user: Any | None, product_ids: Iterable[uuid.UUID]
) -> GroupPricing:
    group = await resolve_customer_group(session, user)
    return await load_group_pricing(session, group, product_ids)


async def customer_price(
    session: AsyncSession, *, product_id: uuid.UUID, reference: Decimal, user: Any
) -> Decimal:
    """What ``user`` pays for one unit whose reference price is ``reference``."""
    pricing = await pricing_for_user(session, user, [product_id])
    return pricing.price(product_id, reference)


def price_publics(publics: Iterable[Any], pricing: GroupPricing) -> None:
    """Rewrite the prices of serialized products (never ORM rows) for a group."""
    if pricing.neutral:
        return
    for public in publics:
        reference = getattr(public, "base_price", None)
        if reference is None:
            continue
        price = pricing.price(public.id, Decimal(reference))
        public.base_price = price
        if getattr(public, "sale_price_cached", None) is not None:
            public.sale_price_cached = price


__all__ = [
    "GroupPricing",
    "apply_discount",
    "customer_price",
    "load_group_pricing",
    "price_publics",
    "pricing_for_user",
    "resolve_customer_group",
]
