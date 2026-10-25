"""Apply a promo code to a checkout (server-authoritative).

The storefront only sends the code; everything else — existence, validity
window, global and per-customer quotas, minimum order, which lines the
target covers, the amount and its split across lines — is decided here, by
the same function for the quote (``GET /cart/me/checkout-quote``) and the
order (``POST /cart/checkout``). The quota is consumed at checkout with one
conditional ``UPDATE`` so two customers cannot both take the last use.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

from sqlalchemy import func, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.discount.models import Discount, DiscountTarget, DiscountType
from app.features.order.models.order import Order
from app.features.product.services.category_tree import category_ancestors_map
from app.utils.money import quantize_amount

ZERO = Decimal("0.00")


class DiscountRefused(Exception):
    """The code cannot be applied; ``reason`` is a stable code, ``message`` French."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class AppliedDiscount:
    """What a code takes off this checkout, line by line."""

    discount_id: uuid.UUID
    code: str
    label: str
    amount: Decimal
    #: Discount carried by each cart line (keyed by cart item id); sums to ``amount``.
    line_amounts: dict[uuid.UUID, Decimal] = field(default_factory=dict)


def normalize_code(code: str | None) -> str:
    """Codes are stored and compared upper-cased, without surrounding blanks."""
    return (code or "").strip().upper()


def _now() -> datetime:
    return datetime.now(UTC)


def eligible_lines(
    discount: Any,
    items: list[Any],
    products_by_id: dict[uuid.UUID, Any],
    category_ancestors: dict[uuid.UUID, tuple[uuid.UUID, ...]] | None = None,
) -> list[Any]:
    """Cart lines the discount's target covers. ``category_ancestors`` (category
    → its ancestors) lets a code on « Réseau » cover the WiFi access points."""
    target = discount.target
    if target == DiscountTarget.ORDER:
        return list(items)
    out = []
    for item in items:
        product = products_by_id.get(item.product_id)
        if product is None:
            continue
        if target == DiscountTarget.PRODUCT and product.id == discount.product_id:
            out.append(item)
        elif target == DiscountTarget.CATEGORY and discount.category_id in _lineage(
            getattr(product, "category_id", None), category_ancestors
        ):
            out.append(item)
    return out


def _lineage(
    category_id: uuid.UUID | None,
    category_ancestors: dict[uuid.UUID, tuple[uuid.UUID, ...]] | None,
) -> tuple[uuid.UUID, ...]:
    """The product's category and its ancestors (empty without a category)."""
    if category_id is None:
        return ()
    return (category_id, *(category_ancestors or {}).get(category_id, ()))


def split_amount(
    total: Decimal, weights: list[tuple[uuid.UUID, Decimal]], currency: str
) -> dict[uuid.UUID, Decimal]:
    """Allocate ``total`` across lines in proportion to their weight.

    Largest-remainder rounding: the per-line parts always sum to ``total``,
    so the order lines and the order agree to the last unit.
    """
    if total <= ZERO or not weights:
        return {key: ZERO for key, _ in weights}
    base = sum((w for _, w in weights), ZERO)
    if base <= ZERO:
        return {key: ZERO for key, _ in weights}
    # Smallest unit of the currency: 1 for XPF, 0.01 for EUR / USD.
    exponent = quantize_amount(ZERO, currency).as_tuple().exponent
    step = Decimal(1).scaleb(int(exponent)) if isinstance(exponent, int) else Decimal(1)
    shares: dict[uuid.UUID, Decimal] = {}
    remainders: list[tuple[Decimal, uuid.UUID]] = []
    allocated = ZERO
    for key, weight in weights:
        exact = total * weight / base
        part = (exact / step).to_integral_value(rounding=ROUND_DOWN) * step
        shares[key] = part
        allocated += part
        remainders.append((exact - part, key))
    left = total - allocated
    for _, key in sorted(remainders, key=lambda r: r[0], reverse=True):
        if left <= ZERO:
            break
        shares[key] += step
        left -= step
    return shares


async def _customer_uses(
    session: AsyncSession, *, discount_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    value = (
        await session.exec(
            select(func.count(col(Order.id))).where(
                col(Order.discount_id) == discount_id,
                col(Order.user_id) == user_id,
            )
        )
    ).one()
    return int(value)


async def resolve_coupon(
    session: AsyncSession,
    *,
    code: str,
    user_id: uuid.UUID,
    items: list[Any],
    products_by_id: dict[uuid.UUID, Any],
    currency: str,
) -> AppliedDiscount:
    """Validate ``code`` for this cart and compute what it takes off.

    Raises :class:`DiscountRefused` with a customer-readable reason.
    """
    normalized = normalize_code(code)
    if not normalized:
        raise DiscountRefused("empty", "Saisissez un code promo")
    result = await session.exec(
        select(Discount).where(
            func.upper(col(Discount.code)) == normalized,
            col(Discount.discount_type) == DiscountType.COUPON,
        )
    )
    discount = result.first()
    if discount is None or not discount.is_active or not discount.is_admin_active:
        raise DiscountRefused("unknown", "Code promo inconnu")
    now = _now()
    if discount.start_date and discount.start_date > now:
        raise DiscountRefused("not_started", "Ce code n'est pas encore valide")
    if discount.end_date and discount.end_date < now:
        raise DiscountRefused("expired", "Ce code a expiré")
    if discount.max_uses is not None and discount.current_uses >= discount.max_uses:
        raise DiscountRefused("exhausted", "Ce code a atteint sa limite d'utilisation")
    if discount.max_uses_per_customer is not None:
        used = await _customer_uses(session, discount_id=discount.id, user_id=user_id)
        if used >= discount.max_uses_per_customer:
            raise DiscountRefused(
                "customer_limit",
                "Vous avez déjà utilisé ce code le nombre de fois permis",
            )

    ancestors = (
        await category_ancestors_map(session)
        if discount.target == DiscountTarget.CATEGORY
        or not getattr(discount, "applies_to_promoted", True)
        else {}
    )
    lines = eligible_lines(discount, items, products_by_id, ancestors)
    if not getattr(discount, "applies_to_promoted", True) and lines:
        # « Non cumulable » : the articles a promotion in force covers are
        # left out of the code (they already have their own reduced price).
        from app.features.product.services.group_pricing import (
            load_active_promotions,
        )

        promotions = await load_active_promotions(session)
        promoted = {
            product_id
            for product_id, product in products_by_id.items()
            if any(
                p.matches(
                    product_id=product_id,
                    parent_id=getattr(product, "parent_product_id", None),
                    category_id=getattr(product, "category_id", None),
                    category_lineage=_lineage(
                        getattr(product, "category_id", None), ancestors
                    ),
                )
                for p in promotions
            )
        }
        kept = [item for item in lines if item.product_id not in promoted]
        if not kept:
            raise DiscountRefused(
                "promoted_only",
                "Ce code ne s'applique pas aux articles déjà en promotion",
            )
        lines = kept
    weights = [
        (item.id, quantize_amount(Decimal(item.unit_price) * item.quantity, currency))
        for item in lines
    ]
    eligible_total = sum((w for _, w in weights), ZERO)
    if eligible_total <= ZERO:
        raise DiscountRefused(
            "not_applicable", "Aucun article du panier n'est concerné par ce code"
        )
    if (
        discount.min_order_amount is not None
        and eligible_total < discount.min_order_amount
    ):
        raise DiscountRefused(
            "below_minimum",
            f"Ce code s'applique à partir de {discount.min_order_amount} {currency} "
            "d'articles concernés",
        )

    if discount.percentage is not None:
        raw = eligible_total * Decimal(discount.percentage) / Decimal("100")
    elif discount.amount is not None:
        raw = Decimal(discount.amount)
    else:
        raise DiscountRefused("misconfigured", "Ce code n'a pas de remise définie")
    amount = min(quantize_amount(raw, currency), eligible_total)
    if amount <= ZERO:
        raise DiscountRefused("zero", "Ce code ne donne aucune remise sur ce panier")

    return AppliedDiscount(
        discount_id=discount.id,
        code=normalize_code(discount.code),
        label=discount.name,
        amount=amount,
        line_amounts=split_amount(amount, weights, currency),
    )


async def consume_coupon(session: AsyncSession, *, discount_id: uuid.UUID) -> None:
    """Take one use, atomically; refuses when the last one just went.

    No commit: part of the checkout transaction, rolled back with it.
    """
    result = await session.execute(
        update(Discount)
        .where(
            col(Discount.id) == discount_id,
            (col(Discount.max_uses).is_(None))
            | (col(Discount.current_uses) < col(Discount.max_uses)),
        )
        .values(current_uses=Discount.current_uses + 1, modify_at=_now())
    )
    if getattr(result, "rowcount", 1) == 0:
        raise DiscountRefused(
            "exhausted", "Ce code vient d'atteindre sa limite d'utilisation"
        )
