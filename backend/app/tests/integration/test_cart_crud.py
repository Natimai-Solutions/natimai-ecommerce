"""Panier (Q3) — ``cart/crud/cart.py`` contre une vraie base.

Couvert à 23 % : le calcul du total, l'incrément d'une ligne existante et le
cliché de taux de change à l'ajout n'étaient vérifiés que de loin, via le
parcours checkout. Ce sont pourtant les montants que le client paie.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.base.crud import RecordNotFoundError
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import Cart, CartItem
from app.features.product.models.currency_rate import (
    CurrencyRate,
    CurrencyRateSource,
)
from app.features.product.models.product import Product
from app.features.user.models.user import User


async def _seed_user(session: AsyncSession) -> uuid.UUID:
    user = User(
        email=f"client+{uuid.uuid4().hex[:8]}@example.pf",
        is_active=True,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    return user.id


async def _seed_product(
    session: AsyncSession, *, price: str, cost_currency: str | None = None
) -> uuid.UUID:
    product = Product(
        name=f"Produit {uuid.uuid4().hex[:4]}",
        base_price=Decimal(price),
        cost_currency=cost_currency or settings.REFERENCE_CURRENCY,
    )
    session.add(product)
    await session.flush()
    return product.id


async def _product(session: AsyncSession, product_id: uuid.UUID) -> Product:
    """Instance fraîche : ``add_or_increment`` commit, ce qui expire celles
    déjà chargées (MissingGreenlet au prochain accès d'attribut)."""
    product = await session.get(Product, product_id)
    assert product is not None
    return product


@pytest.mark.asyncio
async def test_active_cart_is_reused_until_checked_out(
    db_session: AsyncSession,
) -> None:
    user_id = await _seed_user(db_session)

    first = await crud_cart.get_or_create_active_cart(db_session, user_id=user_id)
    again = await crud_cart.get_or_create_active_cart(db_session, user_id=user_id)
    assert again.id == first.id
    assert first.total_amount == Decimal("0.00")
    first_id = first.id

    # Une fois converti en commande, le panier n'est plus « actif » : le
    # prochain appel en ouvre un neuf.
    first.is_checked_out = True
    db_session.add(first)
    await db_session.commit()

    assert await crud_cart.get_active_cart_by_user(db_session, user_id=user_id) is None
    fresh = await crud_cart.get_or_create_active_cart(db_session, user_id=user_id)
    assert fresh.id != first_id


@pytest.mark.asyncio
async def test_sync_total_sums_active_lines_only(db_session: AsyncSession) -> None:
    user_id = await _seed_user(db_session)
    cart = await crud_cart.get_or_create_active_cart(db_session, user_id=user_id)
    cart_id = cart.id
    kept = await _seed_product(db_session, price="1999.50")
    removed = await _seed_product(db_session, price="100.00")

    await crud_cart_item.add_or_increment(
        db_session,
        cart_id=cart_id,
        product=await _product(db_session, kept),
        quantity=2,
    )
    line = await crud_cart_item.add_or_increment(
        db_session,
        cart_id=cart_id,
        product=await _product(db_session, removed),
        quantity=1,
    )
    await crud_cart_item.deactivate_item(db_session, item=line)

    total = await crud_cart.sync_total(db_session, cart_id=cart_id)
    # XPF n'a pas de décimales : 3999.00 quantifié à l'entier.
    assert total == Decimal("3999")
    persisted = await db_session.get(Cart, cart_id)
    assert persisted is not None and persisted.total_amount == Decimal("3999")


@pytest.mark.asyncio
async def test_sync_total_refuses_a_closed_or_unknown_cart(
    db_session: AsyncSession,
) -> None:
    user_id = await _seed_user(db_session)
    cart = await crud_cart.get_or_create_active_cart(db_session, user_id=user_id)
    cart_id = cart.id
    cart.is_checked_out = True
    db_session.add(cart)
    await db_session.commit()

    with pytest.raises(RecordNotFoundError):
        await crud_cart.sync_total(db_session, cart_id=cart_id)
    with pytest.raises(RecordNotFoundError):
        await crud_cart.sync_total(db_session, cart_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_adding_the_same_product_increments_and_refreshes_the_price(
    db_session: AsyncSession,
) -> None:
    """Deux ajouts du même produit font une ligne, pas deux ; et la ligne
    reprend le prix courant du produit, pas celui du premier ajout."""
    user_id = await _seed_user(db_session)
    cart = await crud_cart.get_or_create_active_cart(db_session, user_id=user_id)
    cart_id = cart.id
    product_id = await _seed_product(db_session, price="500.00")

    first = await crud_cart_item.add_or_increment(
        db_session,
        cart_id=cart_id,
        product=await _product(db_session, product_id),
        quantity=1,
    )
    first_id = first.id

    repriced = await _product(db_session, product_id)
    repriced.base_price = Decimal("450.00")
    db_session.add(repriced)
    await db_session.commit()

    second = await crud_cart_item.add_or_increment(
        db_session,
        cart_id=cart_id,
        product=await _product(db_session, product_id),
        quantity=3,
    )
    assert second.id == first_id
    assert second.quantity == 4
    assert second.unit_price == Decimal("450.00")
    assert len(await crud_cart_item.get_by_cart_id(db_session, cart_id=cart_id)) == 1


@pytest.mark.asyncio
async def test_fx_snapshot_is_taken_when_the_cost_is_in_another_currency(
    db_session: AsyncSession,
) -> None:
    """Le taux appliqué est figé sur la ligne : si le taux change avant le
    checkout, on sait à combien le prix a été calculé."""
    db_session.add(
        CurrencyRate(
            currency_code="USD",
            rate_to_reference=Decimal("110.500000"),
            valid_from=datetime.date.today() - datetime.timedelta(days=1),
            source=CurrencyRateSource.manual,
            is_active=True,
        )
    )
    user_id = await _seed_user(db_session)
    cart = await crud_cart.get_or_create_active_cart(db_session, user_id=user_id)
    cart_id = cart.id
    in_usd = await _seed_product(db_session, price="1000.00", cost_currency="USD")
    in_ref = await _seed_product(db_session, price="1000.00")
    in_eur = await _seed_product(db_session, price="1000.00", cost_currency="EUR")

    usd_line = await crud_cart_item.add_or_increment(
        db_session,
        cart_id=cart_id,
        product=await _product(db_session, in_usd),
        quantity=1,
    )
    assert usd_line.fx_source_currency == "USD"
    assert usd_line.fx_rate_used == Decimal("110.500000")

    ref_line = await crud_cart_item.add_or_increment(
        db_session,
        cart_id=cart_id,
        product=await _product(db_session, in_ref),
        quantity=1,
    )
    assert ref_line.fx_source_currency is None
    assert ref_line.fx_rate_used is None

    # Pas de taux EUR : l'ajout n'est pas bloqué, le cliché reste vide.
    eur_line = await crud_cart_item.add_or_increment(
        db_session,
        cart_id=cart_id,
        product=await _product(db_session, in_eur),
        quantity=1,
    )
    assert eur_line.fx_source_currency is None
    assert eur_line.fx_rate_used is None


@pytest.mark.asyncio
async def test_item_lookup_is_scoped_to_the_owner_and_open_carts(
    db_session: AsyncSession,
) -> None:
    """Un client ne doit pas pouvoir modifier la ligne d'un autre en devinant
    son id, ni une ligne d'un panier déjà commandé."""
    owner_id = await _seed_user(db_session)
    other_id = await _seed_user(db_session)
    cart = await crud_cart.get_or_create_active_cart(db_session, user_id=owner_id)
    cart_id = cart.id
    product_id = await _seed_product(db_session, price="10.00")
    line = await crud_cart_item.add_or_increment(
        db_session,
        cart_id=cart_id,
        product=await _product(db_session, product_id),
        quantity=1,
    )
    line_id = line.id

    mine = await crud_cart_item.get_active_item_for_user(
        db_session, item_id=line_id, user_id=owner_id
    )
    assert mine is not None and mine.id == line_id
    assert (
        await crud_cart_item.get_active_item_for_user(
            db_session, item_id=line_id, user_id=other_id
        )
        is None
    )

    updated = await crud_cart_item.update_quantity(db_session, item=mine, quantity=5)
    assert updated.quantity == 5

    closed = await db_session.get(Cart, cart_id)
    assert closed is not None
    closed.is_checked_out = True
    db_session.add(closed)
    await db_session.commit()
    assert (
        await crud_cart_item.get_active_item_for_user(
            db_session, item_id=line_id, user_id=owner_id
        )
        is None
    )


@pytest.mark.asyncio
async def test_clear_cart_deactivates_every_line(db_session: AsyncSession) -> None:
    user_id = await _seed_user(db_session)
    cart = await crud_cart.get_or_create_active_cart(db_session, user_id=user_id)
    cart_id = cart.id
    for price in ("1.00", "2.00", "3.00"):
        product_id = await _seed_product(db_session, price=price)
        await crud_cart_item.add_or_increment(
            db_session,
            cart_id=cart_id,
            product=await _product(db_session, product_id),
            quantity=1,
        )

    assert await crud_cart_item.clear_cart(db_session, cart_id=cart_id) == 3
    assert await crud_cart_item.get_by_cart_id(db_session, cart_id=cart_id) == []
    # Les lignes existent toujours (historique), simplement inactives.
    rows = list((await db_session.exec(select(CartItem))).all())
    assert len(rows) == 3 and all(row.is_active is False for row in rows)
    assert await crud_cart.sync_total(db_session, cart_id=cart_id) == Decimal("0")


@pytest.mark.asyncio
async def test_a_cart_line_is_bounded() -> None:
    """Audit 2026-11: an unbounded quantity overflowed (500)."""
    from pydantic import ValidationError

    from app.features.cart.models.cart import MAX_LINE_QUANTITY, CartItemAddRequest

    with pytest.raises(ValidationError):
        CartItemAddRequest(product_id=uuid.uuid4(), quantity=MAX_LINE_QUANTITY + 1)
    assert CartItemAddRequest(product_id=uuid.uuid4(), quantity=MAX_LINE_QUANTITY)
