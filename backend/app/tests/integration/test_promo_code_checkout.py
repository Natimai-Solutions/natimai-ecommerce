"""Integration: promo codes against a real database.

The case-insensitive lookup, the per-customer quota read from past orders,
and the one-row conditional UPDATE that hands out the last use to exactly
one checkout.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.discount.models import Discount, DiscountTarget, DiscountType
from app.features.discount.services.checkout_discount import (
    DiscountRefused,
    consume_coupon,
    resolve_coupon,
)
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.user.models.user import User


async def _user(session: AsyncSession) -> User:
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    return user


def _items(product_id: uuid.UUID) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id=uuid.uuid4(),
            product_id=product_id,
            unit_price=Decimal("2000"),
            quantity=1,
        )
    ]


@pytest.mark.asyncio
async def test_code_is_found_whatever_the_case_and_the_last_use_goes_once(
    db_session: AsyncSession,
) -> None:
    discount = Discount(
        name="Bienvenue",
        code="BIENVENUE",
        discount_type=DiscountType.COUPON,
        percentage=Decimal("25"),
        target=DiscountTarget.ORDER,
        max_uses=1,
        max_uses_per_customer=1,
    )
    db_session.add(discount)
    await db_session.commit()
    product_id = uuid.uuid4()
    products = {product_id: SimpleNamespace(id=product_id, category_id=None)}
    customer = await _user(db_session)

    applied = await resolve_coupon(
        db_session,
        code="bienvenue",
        user_id=customer.id,
        items=_items(product_id),
        products_by_id=products,
        currency="XPF",
    )
    assert applied.amount == Decimal("500")

    await consume_coupon(db_session, discount_id=discount.id)
    await db_session.commit()
    await db_session.refresh(discount)
    assert discount.current_uses == 1

    with pytest.raises(DiscountRefused) as second:
        await consume_coupon(db_session, discount_id=discount.id)
    assert second.value.reason == "exhausted"
    await db_session.rollback()


@pytest.mark.asyncio
async def test_per_customer_quota_counts_their_past_orders(
    db_session: AsyncSession,
) -> None:
    discount = Discount(
        name="Une fois",
        code="UNEFOIS",
        discount_type=DiscountType.COUPON,
        amount=Decimal("300"),
        target=DiscountTarget.ORDER,
        max_uses_per_customer=1,
    )
    status = OrderStatus(name="Paid")
    customer = await _user(db_session)
    other = await _user(db_session)
    db_session.add_all([discount, status])
    await db_session.flush()
    db_session.add(
        Order(
            user_id=customer.id,
            order_status_id=status.id,
            total_amount=Decimal("1700"),
            subtotal_amount=Decimal("2000"),
            discount_id=discount.id,
            discount_code="UNEFOIS",
            discount_amount=Decimal("300"),
        )
    )
    await db_session.commit()
    product_id = uuid.uuid4()
    products = {product_id: SimpleNamespace(id=product_id, category_id=None)}

    with pytest.raises(DiscountRefused) as refused:
        await resolve_coupon(
            db_session,
            code="UNEFOIS",
            user_id=customer.id,
            items=_items(product_id),
            products_by_id=products,
            currency="XPF",
        )
    assert refused.value.reason == "customer_limit"

    applied = await resolve_coupon(
        db_session,
        code="UNEFOIS",
        user_id=other.id,
        items=_items(product_id),
        products_by_id=products,
        currency="XPF",
    )
    assert applied.amount == Decimal("300")
