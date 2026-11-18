"""Integration (real DB): a retry of the same order submission gets the order
back, never a second one.

D5, review of 17/11/2026: the cart lock only covered two requests at once. A
retry after a timeout found the cart ordered, the storefront rebuilt a cart
from the browser and the checkout created a second order. The storefront now
sends one ``idempotency_key`` per submission."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import cart as cart_routes
from app.api.routes.cart import checkout_my_cart, replace_my_cart_items
from app.features.cart.crud.cart import crud_cart
from app.features.cart.models.cart import (
    Cart,
    CartItem,
    CartReplaceRequest,
    CheckoutRequest,
)
from app.features.inventory.models.inventory import Inventory
from app.features.order.models.order import Order
from app.features.product.models.product import PricingMode, Product
from app.features.user.models.user import User


@pytest.fixture(autouse=True)
def _no_supplier_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def nothing(*_args: Any, **_kwargs: Any) -> dict[Any, Any]:
        return {}

    monkeypatch.setattr(cart_routes, "refresh_supplier_availability", nothing)


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        is_verified=True,
        hashed_password="x",
    )
    product = Product(
        name="Clavier",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("8000"),
        supplier_name="shop",
        supplier_sku=f"k-{uuid.uuid4().hex[:6]}",
    )
    session.add_all([user, product])
    await session.flush()
    session.add(
        Inventory(
            product_id=product.id,
            quantity=Decimal("10.00"),
            compute_from_movements=False,
        )
    )
    ids = (user.id, product.id)
    await session.commit()
    return ids


async def _fill_cart(
    session: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID
) -> None:
    user = await session.get(User, user_id)
    assert user is not None
    await replace_my_cart_items(
        session,
        user,
        CartReplaceRequest.model_validate(
            {"items": [{"product_id": str(product_id), "quantity": 2}]}
        ),
    )


async def _checkout(session: AsyncSession, user_id: uuid.UUID, key: str | None) -> Any:
    user = await session.get(User, user_id)
    assert user is not None
    return await checkout_my_cart(
        session,
        user,
        CheckoutRequest(
            shipping_address="1 rue du Test, Papeete",
            cgv_accepted=True,
            idempotency_key=key,
        ),
    )


async def _orders_of(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.exec(
                select(func.count())
                .select_from(Order)
                .where(col(Order.user_id) == user_id)
            )
        ).one()
    )


@pytest.mark.asyncio
async def test_a_retry_after_a_lost_response_returns_the_same_order(
    db_session: AsyncSession,
) -> None:
    user_id, product_id = await _seed(db_session)
    key = uuid.uuid4().hex

    await _fill_cart(db_session, user_id, product_id)
    first = await _checkout(db_session, user_id, key)
    assert first.replayed is False

    # The response was lost: the storefront mirrors its cart again (a new
    # server cart, the first one is ordered) and submits with the same key.
    await _fill_cart(db_session, user_id, product_id)
    second = await _checkout(db_session, user_id, key)

    assert second.replayed is True
    assert second.order_id == first.order_id
    assert second.order_number == first.order_number
    assert second.total_amount == first.total_amount
    assert second.item_count == first.item_count
    assert await _orders_of(db_session, user_id) == 1
    # The cart the retry rebuilt is emptied: those articles are ordered.
    rebuilt = (
        await db_session.exec(
            select(CartItem)
            .join(Cart, col(Cart.id) == col(CartItem.cart_id))
            .where(
                col(Cart.user_id) == user_id,
                col(Cart.is_checked_out).is_(False),
                col(CartItem.is_active).is_(True),
            )
        )
    ).all()
    assert rebuilt == []


@pytest.mark.asyncio
async def test_a_new_submission_makes_a_new_order(db_session: AsyncSession) -> None:
    user_id, product_id = await _seed(db_session)

    await _fill_cart(db_session, user_id, product_id)
    first = await _checkout(db_session, user_id, uuid.uuid4().hex)
    await _fill_cart(db_session, user_id, product_id)
    second = await _checkout(db_session, user_id, uuid.uuid4().hex)

    assert second.replayed is False and second.order_id != first.order_id
    assert await _orders_of(db_session, user_id) == 2


@pytest.mark.asyncio
async def test_a_key_belongs_to_one_customer(db_session: AsyncSession) -> None:
    alice, product_id = await _seed(db_session)
    bob, _ = await _seed(db_session)
    key = uuid.uuid4().hex

    await _fill_cart(db_session, alice, product_id)
    theirs = await _checkout(db_session, alice, key)
    await _fill_cart(db_session, bob, product_id)
    mine = await _checkout(db_session, bob, key)

    assert mine.replayed is False and mine.order_id != theirs.order_id


@pytest.mark.asyncio
async def test_an_attempt_that_raced_past_the_lookup_is_caught_by_the_index(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two attempts in flight: the second looked before the first committed.
    Writing the key then waits for the first and fails on the unique index —
    before any stock or payment — and the first's order comes back."""
    user_id, product_id = await _seed(db_session)
    key = uuid.uuid4().hex
    await _fill_cart(db_session, user_id, product_id)
    first = await _checkout(db_session, user_id, key)

    real_lookup = cart_routes._order_for_checkout_key
    calls = {"n": 0}

    async def blind_first(*args: Any, **kwargs: Any) -> uuid.UUID | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # the race: the first order is not visible yet
        return await real_lookup(*args, **kwargs)

    monkeypatch.setattr(cart_routes, "_order_for_checkout_key", blind_first)
    await _fill_cart(db_session, user_id, product_id)
    second = await _checkout(db_session, user_id, key)

    assert calls["n"] == 2
    assert second.replayed is True and second.order_id == first.order_id
    assert await _orders_of(db_session, user_id) == 1
    inventory = (
        await db_session.exec(
            select(Inventory).where(col(Inventory.product_id) == product_id)
        )
    ).one()
    await db_session.refresh(inventory)
    # Only the first order reserved its two units.
    assert inventory.quantity == Decimal("8.00")


@pytest.mark.asyncio
async def test_a_double_click_on_the_same_cart_gets_the_order_back(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second click waited on the cart lock and finds the cart ordered:
    with the same key, that is its order, not « already checked out »."""
    user_id, product_id = await _seed(db_session)
    key = uuid.uuid4().hex
    await _fill_cart(db_session, user_id, product_id)
    first = await _checkout(db_session, user_id, key)

    # Replay the second click as it was: same (now ordered) cart, and its
    # early lookup ran before the first order was visible.
    ordered = await db_session.get(Cart, first.cart_id)
    assert ordered is not None and ordered.is_checked_out

    real_active_cart = crud_cart.get_active_cart_by_user
    served = {"n": 0}

    async def same_cart(*args: Any, **kwargs: Any) -> Cart | None:
        served["n"] += 1
        if served["n"] == 1:
            return ordered
        return await real_active_cart(*args, **kwargs)

    real_lookup = cart_routes._order_for_checkout_key
    calls = {"n": 0}

    async def blind_first(*args: Any, **kwargs: Any) -> uuid.UUID | None:
        calls["n"] += 1
        return None if calls["n"] == 1 else await real_lookup(*args, **kwargs)

    monkeypatch.setattr(crud_cart, "get_active_cart_by_user", same_cart)
    monkeypatch.setattr(cart_routes, "_order_for_checkout_key", blind_first)
    second = await _checkout(db_session, user_id, key)

    assert second.replayed is True and second.order_id == first.order_id
    assert await _orders_of(db_session, user_id) == 1


@pytest.mark.asyncio
async def test_the_order_address_is_built_by_the_server(
    db_session: AsyncSession,
) -> None:
    """Review of 17/11/2026: the storefront composed the order's address text
    (recipient and phone inside, capped at 500) and the invoice took it as
    the buyer's address. Built from the saved address now; the recipient and
    the phone have their own columns."""
    from app.features.user.models.address import Address

    user_id, product_id = await _seed(db_session)
    address = Address(
        user_id=user_id,
        type="shipping",
        recipient_name="Teva Tane",
        company="Atelier Moana",
        phone="+689 87 00 00 00",
        street="4 allée des Tiare",
        postal_code="98713",
        city="Papeete",
        country="PF",
    )
    db_session.add(address)
    await db_session.flush()
    address_id = address.id
    await db_session.commit()
    await _fill_cart(db_session, user_id, product_id)
    user = await db_session.get(User, user_id)
    assert user is not None

    placed = await checkout_my_cart(
        db_session,
        user,
        CheckoutRequest(
            shipping_address="whatever the browser typed",
            shipping_address_id=address_id,
            cgv_accepted=True,
        ),
    )

    order = await db_session.get(Order, placed.order_id)
    assert order is not None
    assert (
        order.shipping_address == "Atelier Moana, 4 allée des Tiare, 98713 Papeete, PF"
    )
    assert order.shipping_recipient == "Teva Tane"
    assert order.shipping_phone == "+689 87 00 00 00"
