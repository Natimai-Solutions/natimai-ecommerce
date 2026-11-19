"""Integration tests (real DB): the personal sections of the homepage
(chantier accueil et messagerie, lot A5 / R9) — what the customer bought,
their wishlist, their order in progress; never on a visitor's page."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi import Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.homepage import create_block, get_homepage, get_personal_homepage
from app.api.routes.product_catalog import products_by_ids
from app.features.content.models import HomepageBlockWrite
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.product import PricingMode, Product
from app.features.user.models.user import User
from app.features.user.models.wishlist import Wishlist, WishlistItem
from app.tests.integration.test_media_and_homepage import _admin, _fresh, _request

pytestmark = pytest.mark.asyncio


def _product(name: str) -> Product:
    return Product(
        name=name,
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("10000"),
        is_enriched=True,
        weight=1.0,
        customs_rate_pct=Decimal("0"),
    )


async def _section(session: AsyncSession, admin: User, source: str) -> None:
    await create_block(
        HomepageBlockWrite.model_validate(
            {"kind": "personal", "is_published": True, "config": {"source": source}}
        ),
        _request(),
        session,
        await _fresh(session, admin),
    )


async def test_personal_sections_for_the_customer_only(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    bought, wished, gone = _product("Écran"), _product("Souris"), _product("Ancien")
    gone.is_active = False
    customer = User(
        email=f"c+{uuid.uuid4().hex[:6]}@t.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    pending = OrderStatus(name="Paid")
    done = OrderStatus(name="Delivered")
    db_session.add_all([bought, wished, gone, customer, pending, done])
    await db_session.flush()
    old = Order(
        user_id=customer.id,
        order_status_id=done.id,
        order_number="CMD-OLD",
        total_amount=Decimal("1"),
        subtotal_amount=Decimal("1"),
    )
    current = Order(
        user_id=customer.id,
        order_status_id=pending.id,
        order_number="CMD-NOW",
        total_amount=Decimal("25000"),
        subtotal_amount=Decimal("25000"),
        currency="XPF",
    )
    db_session.add_all([old, current])
    await db_session.flush()
    wishlist = Wishlist(user_id=customer.id, name="Mes envies")
    db_session.add_all(
        [
            OrderLine(
                order_id=old.id,
                product_id=bought.id,
                quantity=1,
                unit_price=Decimal("1"),
            ),
            OrderLine(
                order_id=old.id, product_id=gone.id, quantity=1, unit_price=Decimal("1")
            ),
            wishlist,
        ]
    )
    await db_session.flush()
    db_session.add(WishlistItem(wishlist_id=wishlist.id, product_id=wished.id))
    ids = {"customer": customer.id, "bought": bought.id, "wished": wished.id}
    await db_session.commit()
    for source in ("recently_viewed", "reorder", "wishlist", "current_order"):
        await _section(db_session, admin, source)

    visitor = await get_homepage(_request(), db_session)
    # A visitor only gets the browser's own section.
    assert [s.config["source"] for s in visitor.sections] == ["recently_viewed"]

    user = await db_session.get(User, ids["customer"])
    assert user is not None
    page = await get_personal_homepage(_request(), Response(), db_session, user)
    by_source: dict[str, Any] = {s.config["source"]: s for s in page.sections}
    assert [p.id for p in by_source["reorder"].products] == [ids["bought"]]
    assert [p.id for p in by_source["wishlist"].products] == [ids["wished"]]
    assert by_source["current_order"].current_order.order_number == "CMD-NOW"

    # « Recently viewed »: the browser's list, a product gone left out.
    found = await products_by_ids(db_session, [ids["wished"], uuid.uuid4()], None)
    assert [p.id for p in found] == [ids["wished"]]


async def test_adding_to_the_wishlist_answers_the_list(
    db_session: AsyncSession,
) -> None:
    """The write commits before the answer is built: the route used to read
    the expired list (MissingGreenlet, a 500 though the item was added)."""
    from app.api.routes.user_wishlist import (
        add_product_to_my_wishlist,
        remove_product_from_my_wishlist,
    )
    from app.features.user.models.wishlist import WishlistItemAddRequest

    product = _product("Clavier")
    customer = User(email=f"w+{uuid.uuid4().hex[:6]}@t.local", hashed_password="x")
    db_session.add_all([product, customer])
    ids = (product.id, customer.id)
    await db_session.commit()
    user = await db_session.get(User, ids[1])
    assert user is not None
    added = await add_product_to_my_wishlist(
        db_session, user, WishlistItemAddRequest(product_id=ids[0])
    )
    assert [item.product_id for item in added.items] == [ids[0]]
    user = await db_session.get(User, ids[1])
    assert user is not None
    removed = await remove_product_from_my_wishlist(db_session, user, ids[0])
    assert removed.items == []
