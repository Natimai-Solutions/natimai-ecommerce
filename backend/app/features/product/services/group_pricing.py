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

**Promotions — the best price wins** (decision of 30/09/2026). A promotion
(``Discount`` of type ``promotion``: an article or a category, a percentage
or an amount off, start and end dates) lowers the reference price for
everyone. The customer pays the **lowest** of their group price and the
promotional price — a promotion never stacks on the group discount. When the
promotion wins, the group price is shown struck through.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.discount.models import Discount, DiscountTarget, DiscountType
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
class ActivePromotion:
    """A promotion in force, detached from the ORM."""

    id: uuid.UUID
    name: str
    product_id: uuid.UUID | None
    category_id: uuid.UUID | None
    percentage: Decimal | None
    amount: Decimal | None
    end_date: datetime | None

    def matches(
        self,
        *,
        product_id: uuid.UUID,
        parent_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
    ) -> bool:
        if self.product_id is not None:
            return self.product_id in (product_id, parent_id)
        return self.category_id is not None and self.category_id == category_id

    def apply(self, reference: Decimal) -> Decimal:
        if self.percentage is not None:
            return apply_discount(reference, self.percentage)
        if self.amount is not None:
            return max(reference - Decimal(self.amount), Decimal("0")).quantize(_CENT)
        return reference


@dataclass(frozen=True)
class PriceQuote:
    """What a customer pays for one unit, and why."""

    price: Decimal
    #: Their price without the promotion (group price): struck through when
    #: the promotion wins.
    regular: Decimal
    promotion: ActivePromotion | None = None


@dataclass(frozen=True)
class GroupPricing:
    """One group's discount and typed prices, plus the promotions in force."""

    group_id: uuid.UUID | None
    discount_pct: Decimal = Decimal("0")
    prices: dict[uuid.UUID, Decimal] = field(default_factory=dict)
    promotions: tuple[ActivePromotion, ...] = ()

    @property
    def neutral(self) -> bool:
        return not self.discount_pct and not self.prices and not self.promotions

    def quote(
        self,
        product_id: uuid.UUID,
        reference: Decimal,
        *,
        parent_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
    ) -> PriceQuote:
        """The best price: group price (typed, else discount) vs promotions."""
        typed = self.prices.get(product_id)
        regular = (
            typed if typed is not None else apply_discount(reference, self.discount_pct)
        )
        best: ActivePromotion | None = None
        best_price = regular
        if reference > 0:
            for promotion in self.promotions:
                if not promotion.matches(
                    product_id=product_id, parent_id=parent_id, category_id=category_id
                ):
                    continue
                promo_price = promotion.apply(reference)
                if promo_price < best_price:
                    best, best_price = promotion, promo_price
        return PriceQuote(price=best_price, regular=regular, promotion=best)

    def price(
        self,
        product_id: uuid.UUID,
        reference: Decimal,
        *,
        parent_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
    ) -> Decimal:
        return self.quote(
            product_id, reference, parent_id=parent_id, category_id=category_id
        ).price


async def load_active_promotions(
    session: AsyncSession, *, at: datetime | None = None
) -> tuple[ActivePromotion, ...]:
    """Promotions in force now: an article or a category, a rate or an amount."""
    now = at or datetime.now(timezone.utc)
    rows = await session.exec(
        select(Discount).where(
            col(Discount.discount_type) == DiscountType.PROMOTION,
            col(Discount.is_active).is_(True),
            col(Discount.is_admin_active).is_(True),
            col(Discount.target).in_([DiscountTarget.PRODUCT, DiscountTarget.CATEGORY]),
            (col(Discount.start_date).is_(None)) | (col(Discount.start_date) <= now),
            (col(Discount.end_date).is_(None)) | (col(Discount.end_date) >= now),
        )
    )
    promotions = []
    for row in rows.all():
        if row.percentage is None and row.amount is None:
            continue
        product_id = row.product_id if row.target == DiscountTarget.PRODUCT else None
        category_id = row.category_id if row.target == DiscountTarget.CATEGORY else None
        if product_id is None and category_id is None:
            continue
        promotions.append(
            ActivePromotion(
                id=row.id,
                name=row.name,
                product_id=product_id,
                category_id=category_id,
                percentage=Decimal(row.percentage) if row.percentage else None,
                amount=Decimal(row.amount) if row.amount else None,
                end_date=row.end_date,
            )
        )
    return tuple(promotions)


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
    """The group's discount, its typed prices for ``product_ids`` and the
    promotions in force."""
    promotions = await load_active_promotions(session)
    if group is None:
        return GroupPricing(group_id=None, promotions=promotions)
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
        promotions=promotions,
    )


async def pricing_for_user(
    session: AsyncSession, user: Any | None, product_ids: Iterable[uuid.UUID]
) -> GroupPricing:
    group = await resolve_customer_group(session, user)
    return await load_group_pricing(session, group, product_ids)


async def customer_price(
    session: AsyncSession, *, product: Any, reference: Decimal, user: Any
) -> Decimal:
    """What ``user`` pays for one unit of ``product`` (reference ``reference``)."""
    pricing = await pricing_for_user(session, user, [product.id])
    return pricing.price(
        product.id,
        reference,
        parent_id=getattr(product, "parent_product_id", None),
        category_id=getattr(product, "category_id", None),
    )


def price_publics(publics: Iterable[Any], pricing: GroupPricing) -> None:
    """Rewrite the prices of serialized products (never ORM rows) for a
    customer: group price or promotion, whichever is lower."""
    if pricing.neutral:
        return
    for public in publics:
        reference = getattr(public, "base_price", None)
        if reference is None:
            continue
        quote = pricing.quote(
            public.id,
            Decimal(reference),
            parent_id=getattr(public, "parent_product_id", None),
            category_id=getattr(public, "category_id", None),
        )
        public.base_price = quote.price
        if getattr(public, "sale_price_cached", None) is not None:
            public.sale_price_cached = quote.price
        if quote.promotion is not None:
            public.regular_price = quote.regular
            public.promotion_name = quote.promotion.name
            public.promotion_ends_at = quote.promotion.end_date


__all__ = [
    "ActivePromotion",
    "GroupPricing",
    "PriceQuote",
    "load_active_promotions",
    "apply_discount",
    "customer_price",
    "load_group_pricing",
    "price_publics",
    "pricing_for_user",
    "resolve_customer_group",
]
