"""Integration (real DB, two sessions): two checkouts of the last unit sell
it once — the reservation reads the stock under the row locks of
``lock_stock_rows``, as the checkout does."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import cart as cart_routes
from app.core.errors import AppError
from app.features.inventory.crud import crud_inventory
from app.features.inventory.models.inventory import Inventory
from app.features.inventory.services.stock_release import lock_stock_rows
from app.features.product.models.product import Product
from app.features.user.models.user import User


@pytest.mark.asyncio
async def test_the_last_unit_is_reserved_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(email=f"buyer+{uuid.uuid4().hex[:8]}@test.local", hashed_password="x")
    product = Product(name="Écran", base_price=Decimal("25000"))
    db_session.add_all([user, product])
    await db_session.flush()
    db_session.add(
        Inventory(
            product_id=product.id,
            place_id=None,
            quantity=Decimal("1.00"),
            compute_from_movements=False,
        )
    )
    user_id, product_id = user.id, product.id
    await db_session.commit()

    # Both checkouts meet right after reading the stock: without the locks,
    # both would read 1 and both reserve it.
    read_stock = crud_inventory.get_by_product_and_place
    barrier = asyncio.Barrier(2)

    async def read_then_meet(*args: Any, **kwargs: Any) -> Any:
        found = await read_stock(*args, **kwargs)
        try:
            await asyncio.wait_for(barrier.wait(), timeout=0.5)
        except TimeoutError:
            pass
        return found

    monkeypatch.setattr(crud_inventory, "get_by_product_and_place", read_then_meet)

    async def checkout() -> Any:
        async with AsyncSession(db_session.bind, expire_on_commit=False) as session:
            await lock_stock_rows(session, [product_id])
            buyer = await session.get(User, user_id)
            item = await session.get(Product, product_id)
            assert buyer is not None and item is not None
            reserved = await cart_routes._reserve_stock_for_checkout(
                session,
                order_id=uuid.uuid4(),
                product=item,
                quantity=1,
                current_user=buyer,
            )
            await session.commit()
            return reserved

    outcomes = await asyncio.gather(checkout(), checkout(), return_exceptions=True)

    refused = [o for o in outcomes if isinstance(o, AppError)]
    assert len(refused) == 1, outcomes
    assert refused[0].code.startswith("cart.stock.")
    stock = await read_stock(db_session, product_id=product_id, place_id=None)
    assert stock is not None
    await db_session.refresh(stock)
    assert stock.quantity == Decimal("0")
