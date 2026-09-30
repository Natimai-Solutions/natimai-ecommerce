"""Integration tests: replacing the cart content is atomic.

The storefront cart lives in the browser and was mirrored into the backend at
checkout time by a DELETE followed by one POST per line. That sequence was not
transactional — a failure midway left a truncated backend cart that the
checkout then ordered as if it were complete — and it was not a merge either:
the clear destroyed whatever the account already had.
"""

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import replace_my_cart_items
from app.core.errors import AppError
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import CartItemAddRequest, CartReplaceRequest
from app.features.product.models.product import Product
from app.features.product.services.pricing import calculate_sale_price
from app.features.user.models.user import User


async def _user(session: AsyncSession) -> uuid.UUID:
    """Return the id, not the instance: a commit expires ORM objects."""
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    return user.id


async def _product(
    session: AsyncSession, *, price: str = "1000.00", active: bool = True
) -> uuid.UUID:
    product = Product(
        name=f"Produit {uuid.uuid4().hex[:6]}",
        base_price=Decimal(price),
        is_active=active,
        is_supplier_managed=False,
        weight=1.0,
        customs_rate_pct=Decimal("0.00"),
    )
    session.add(product)
    await session.flush()
    return product.id


async def _replace(
    session: AsyncSession, user_id: uuid.UUID, entries: list[tuple[uuid.UUID, int]]
) -> None:
    user = await session.get(User, user_id)
    assert user is not None
    await replace_my_cart_items(
        session=session,
        current_user=user,
        payload=CartReplaceRequest(
            items=[
                CartItemAddRequest(product_id=product_id, quantity=quantity)
                for product_id, quantity in entries
            ]
        ),
    )


async def _cart_contents(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    cart = await crud_cart.get_active_cart_by_user(session=session, user_id=user_id)
    assert cart is not None
    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    return {item.product_id: item.quantity for item in items}


@pytest.mark.asyncio
async def test_replace_installs_the_whole_content(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    first = await _product(db_session)
    second = await _product(db_session)
    await db_session.commit()

    await _replace(db_session, user_id, [(first, 2), (second, 3)])

    assert await _cart_contents(db_session, user_id) == {first: 2, second: 3}


@pytest.mark.asyncio
async def test_replace_drops_the_previous_content(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    old_product = await _product(db_session)
    new_product = await _product(db_session)
    await db_session.commit()

    await _replace(db_session, user_id, [(old_product, 1)])
    await _replace(db_session, user_id, [(new_product, 4)])

    assert await _cart_contents(db_session, user_id) == {new_product: 4}


@pytest.mark.asyncio
async def test_repeated_products_are_merged(db_session: AsyncSession) -> None:
    """One row per product is an invariant of the cart."""
    user_id = await _user(db_session)
    product = await _product(db_session)
    await db_session.commit()

    await _replace(db_session, user_id, [(product, 2), (product, 3)])

    assert await _cart_contents(db_session, user_id) == {product: 5}


@pytest.mark.asyncio
async def test_an_unavailable_product_leaves_the_cart_untouched(
    db_session: AsyncSession,
) -> None:
    """The whole call applies or nothing does — no truncated cart."""
    user_id = await _user(db_session)
    good = await _product(db_session)
    kept = await _product(db_session)
    withdrawn = await _product(db_session, active=False)
    await db_session.commit()

    await _replace(db_session, user_id, [(kept, 7)])

    with pytest.raises(AppError) as excinfo:
        await _replace(db_session, user_id, [(good, 1), (withdrawn, 1)])
    assert excinfo.value.code == "cart.product.not_found"

    # The pre-existing content survived: nothing was cleared before validating.
    assert await _cart_contents(db_session, user_id) == {kept: 7}


@pytest.mark.asyncio
async def test_an_empty_payload_empties_the_cart(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    product = await _product(db_session)
    await db_session.commit()

    await _replace(db_session, user_id, [(product, 1)])
    await _replace(db_session, user_id, [])

    assert await _cart_contents(db_session, user_id) == {}


@pytest.mark.asyncio
async def test_lines_are_priced_by_the_server(db_session: AsyncSession) -> None:
    """The snapshot is the recomputed sale price, never a caller-supplied one."""
    user_id = await _user(db_session)
    product_id = await _product(db_session, price="2500.00")
    await db_session.commit()

    await _replace(db_session, user_id, [(product_id, 2)])

    product = await db_session.get(Product, product_id)
    assert product is not None
    expected = await calculate_sale_price(db_session, product)

    cart = await crud_cart.get_active_cart_by_user(session=db_session, user_id=user_id)
    assert cart is not None
    items = await crud_cart_item.get_by_cart_id(session=db_session, cart_id=cart.id)
    assert items[0].unit_price == expected


@pytest.mark.asyncio
async def test_replace_is_repeatable(db_session: AsyncSession) -> None:
    """Re-sending the same content must not accumulate rows."""
    user_id = await _user(db_session)
    product = await _product(db_session)
    await db_session.commit()

    await _replace(db_session, user_id, [(product, 3)])
    await _replace(db_session, user_id, [(product, 3)])

    assert await _cart_contents(db_session, user_id) == {product: 3}
