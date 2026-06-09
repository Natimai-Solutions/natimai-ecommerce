"""Payment method eligibility helpers.

Rules:
- A method with NO eligibility rows is available to every price group (open default).
- A method with at least one eligibility row is restricted to the listed groups only.
- max_amount (when set) further restricts the method: if the cart total exceeds it,
  the method is hidden from the listing and blocked at initiation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.models.payment_method_eligibility import (
    PaymentMethodEligibility,
)
from app.features.product.models.price_group import PriceGroup


async def get_default_price_group_id(session: AsyncSession) -> uuid.UUID | None:
    """Return the id of the price group flagged as default, if any."""
    result = await session.exec(
        select(PriceGroup).where(PriceGroup.default == True).limit(1)  # noqa: E712
    )
    pg = result.first()
    return pg.id if pg else None


async def get_eligible_payment_methods(
    session: AsyncSession,
    *,
    price_group_id: uuid.UUID | None,
    cart_total: Decimal | None = None,
) -> list[PaymentMethod]:
    """Return active payment methods available to a given price group.

    If price_group_id is None, falls back to the default price group;
    if no default exists, returns only methods with no eligibility restriction.

    cart_total, if provided, filters out methods whose max_amount is exceeded.
    """
    resolved_group_id = price_group_id
    if resolved_group_id is None:
        resolved_group_id = await get_default_price_group_id(session)

    # Fetch all active methods
    stmt = select(PaymentMethod).where(
        PaymentMethod.is_active == True,  # noqa: E712
        PaymentMethod.is_admin_active == True,  # noqa: E712
    )
    result = await session.exec(stmt)
    all_active: list[PaymentMethod] = list(result.all())

    if not all_active:
        return []

    # Fetch methods that have at least one eligibility restriction
    restricted_ids_stmt = select(PaymentMethodEligibility.payment_method_id).distinct()
    restricted_result = await session.exec(restricted_ids_stmt)
    restricted_method_ids: set[uuid.UUID] = set(restricted_result.all())

    # Fetch methods allowed for this group
    allowed_ids: set[uuid.UUID] = set()
    if resolved_group_id is not None:
        allowed_stmt = select(PaymentMethodEligibility.payment_method_id).where(
            PaymentMethodEligibility.price_group_id == resolved_group_id
        )
        allowed_result = await session.exec(allowed_stmt)
        allowed_ids = set(allowed_result.all())

    eligible: list[PaymentMethod] = []
    for method in all_active:
        # Open default: no eligibility rows → available to all
        if method.id not in restricted_method_ids:
            eligible.append(method)
        elif method.id in allowed_ids:
            eligible.append(method)

    # Apply max_amount filter
    if cart_total is not None:
        eligible = [
            m for m in eligible if m.max_amount is None or m.max_amount >= cart_total
        ]

    return sorted(eligible, key=lambda m: m.sort_order)


async def check_payment_method_eligible(
    session: AsyncSession,
    *,
    payment_method_id: uuid.UUID,
    price_group_id: uuid.UUID | None,
    amount: Decimal,
) -> bool:
    """Return True if the payment method is eligible for this group and amount."""
    eligible = await get_eligible_payment_methods(
        session,
        price_group_id=price_group_id,
        cart_total=amount,
    )
    return any(m.id == payment_method_id for m in eligible)
