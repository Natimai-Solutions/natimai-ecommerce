"""Integration (real DB): a buyer reviews a product, the shop moderates, the
product page shows the approved reviews and their summary."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.reviews import (
    ModerationDecision,
    ReviewWrite,
    get_my_review,
    list_published_product_reviews,
    list_reviews_to_moderate,
    moderate,
    put_my_review,
)
from app.core.errors import AppError
from app.core.security import get_password_hash
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.product import PricingMode, Product
from app.features.user.models.review import ReviewStatus
from app.features.user.models.user import User


async def _user(db_session: AsyncSession, name: str, *, admin: bool = False) -> User:
    user = User(
        email=f"u+{uuid.uuid4().hex[:8]}@test.local",
        full_name=name,
        is_active=True,
        is_verified=True,
        is_superuser=admin,
        hashed_password=get_password_hash("mot-de-passe-client"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _bought(
    db_session: AsyncSession, user: User, product_id: uuid.UUID, status: str = "Paid"
) -> None:
    await db_session.refresh(user)
    row: Any = (
        await db_session.exec(
            select(OrderStatus).where(col(OrderStatus.name) == status)
        )
    ).first()
    if row is None:
        row = OrderStatus(name=status)
        db_session.add(row)
        await db_session.flush()
    order = Order(
        user_id=user.id,
        order_status_id=row.id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("9000"),
        total_amount=Decimal("9000"),
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        OrderLine(
            order_id=order.id,
            product_id=product_id,
            quantity=1,
            unit_price=Decimal("9000"),
        )
    )
    await db_session.commit()


def _product(name: str, parent_id: uuid.UUID | None = None) -> Product:
    return Product(
        name=name,
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("9000"),
        supplier_name="shop",
        supplier_sku=f"s-{uuid.uuid4().hex[:6]}",
        parent_product_id=parent_id,
    )


@pytest.mark.asyncio
async def test_a_buyer_reviews_and_the_shop_publishes(db_session: AsyncSession) -> None:
    buyer = await _user(db_session, "Hina Teriitahi")
    other = await _user(db_session, "Marc Dupont")
    admin = await _user(db_session, "Admin Boutique", admin=True)
    product = _product("Clavier")
    db_session.add(product)
    await db_session.flush()
    product_id = product.id
    await db_session.commit()
    await _bought(db_session, buyer, product_id)
    await _bought(db_session, other, product_id)

    await db_session.refresh(buyer)
    state = await get_my_review(product_id, db_session, buyer)
    assert state.can_review is True and state.review is None

    await db_session.refresh(buyer)
    written = await put_my_review(
        product_id, ReviewWrite(rating=5, comment="  Parfait.  "), db_session, buyer
    )
    assert written.review is not None
    assert written.review.status == ReviewStatus.PENDING.value
    assert written.review.comment == "Parfait."
    await db_session.refresh(other)
    await put_my_review(product_id, ReviewWrite(rating=3), db_session, other)

    # Nothing shows before moderation.
    page = await list_published_product_reviews(product_id, db_session)
    assert page.summary.count == 0 and page.data == []

    await db_session.refresh(admin)
    pending = await list_reviews_to_moderate(db_session)
    assert pending.count == 2
    by_author = {r.author_name: r for r in pending.data}
    assert set(by_author) == {"Hina T.", "Marc D."}
    assert all(r.verified_purchase for r in pending.data)

    await moderate(
        by_author["Hina T."].id,
        ModerationDecision(decision="approve"),
        db_session,
        admin,
    )
    await db_session.refresh(admin)
    rejected = await moderate(
        by_author["Marc D."].id,
        ModerationDecision(decision="reject", note="Hors sujet"),
        db_session,
        admin,
    )
    assert rejected.status == "rejected" and rejected.moderation_note == "Hors sujet"

    page = await list_published_product_reviews(product_id, db_session)
    assert page.summary.count == 1 and page.summary.average == 5.0
    assert page.summary.distribution["5"] == 1
    assert [(r.author_name, r.rating) for r in page.data] == [("Hina T.", 5)]
    # The public view never carries who wrote it beyond the display name.
    assert "user_id" not in page.data[0].model_dump()

    # Edited: back to moderation, hidden again.
    await db_session.refresh(buyer)
    edited = await put_my_review(product_id, ReviewWrite(rating=4), db_session, buyer)
    assert edited.review is not None and edited.review.status == "pending"
    assert (
        await list_published_product_reviews(product_id, db_session)
    ).summary.count == 0


@pytest.mark.asyncio
async def test_only_a_buyer_may_review_variants_included(
    db_session: AsyncSession,
) -> None:
    buyer = await _user(db_session, "Hina Teriitahi")
    browser = await _user(db_session, "Visiteur")
    unpaid = await _user(db_session, "Pas Payé")
    parent = _product("Portable")
    db_session.add(parent)
    await db_session.flush()
    variant = _product("Portable 16 Go", parent_id=parent.id)
    db_session.add(variant)
    await db_session.flush()
    parent_id, variant_id = parent.id, variant.id
    await db_session.commit()
    # Bought the variant: may review the listed parent.
    await _bought(db_session, buyer, variant_id)
    # Ordered but never paid.
    await _bought(db_session, unpaid, parent_id, status="Pending")

    await db_session.refresh(buyer)
    assert (await get_my_review(parent_id, db_session, buyer)).can_review is True

    for user in (browser, unpaid):
        await db_session.refresh(user)
        assert (await get_my_review(parent_id, db_session, user)).can_review is False
        with pytest.raises(AppError) as refused:
            await put_my_review(parent_id, ReviewWrite(rating=1), db_session, user)
        assert refused.value.code == "review.not_purchased"
        assert refused.value.status_code == 403
