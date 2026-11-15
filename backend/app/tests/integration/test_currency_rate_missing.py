"""Integration (real DB): a cost in a currency with no rate in force.

Functional audit, November 2026: the product stayed publishable, its page and
the cart answered 500, and one such article in a list failed the whole
request."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import add_cart_item
from app.core.errors import AppError
from app.features.cart.models.cart import CartItemAddRequest
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product
from app.features.product.services.publication import (
    CURRENCY_RATE_MISSING,
    publication_blockers,
)
from app.features.user.models.user import User


@pytest.mark.asyncio
async def test_a_product_without_a_rate_is_neither_opened_nor_sold(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    orphan = Product(
        name="Sans taux",
        base_price=Decimal("100"),
        cost_amount=Decimal("100"),
        cost_currency="ZZZ",  # no CurrencyRate
        weight=1.0,
        customs_rate_pct=Decimal("0"),
    )
    priced = Product(
        name="Avec prix",
        base_price=Decimal("1000"),
        cost_amount=Decimal("1000"),
        cost_currency="XPF",
        weight=1.0,
        customs_rate_pct=Decimal("0"),
        margin_rate_pct=Decimal("0"),
    )
    db_session.add_all([user, orphan, priced])
    await db_session.flush()
    orphan_id = orphan.id
    await db_session.commit()

    reloaded = await db_session.get(Product, orphan_id)
    assert reloaded is not None
    assert CURRENCY_RATE_MISSING in await publication_blockers(db_session, reloaded)

    # In a list, the article is unpriced; the others keep their price.
    await db_session.refresh(priced)
    rows = [reloaded, priced]
    await crud_product._apply_runtime_sale_prices(db_session, rows)  # noqa: SLF001
    assert rows[0].base_price == Decimal("0") and rows[1].base_price > 0
    await db_session.rollback()

    # The cart refuses it with an answer the storefront can show.
    await db_session.refresh(user)
    with pytest.raises(AppError) as refused:
        await add_cart_item(
            session=db_session,
            current_user=user,
            payload=CartItemAddRequest(product_id=orphan_id, quantity=1),
        )
    assert refused.value.code == "cart.product.not_purchasable"
    assert CURRENCY_RATE_MISSING in refused.value.details["blockers"]
