"""Integration (real DB): the import mode the customer paid for follows the
order.

Review of 17/11/2026: ``order_lines.import_service_level`` was written at
checkout and read by no screen — the shop could not tell by which mode to
ship — and it was lost through a quote and a « commander à nouveau »."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import cart as cart_routes
from app.api.routes.admin_orders import get_order_detail
from app.api.routes.cart import reorder_into_cart
from app.features.cart.models.cart import Cart
from app.features.cart.models.quote_request import QuoteRequest
from app.features.cart.services.quote import (
    proposed_lines,
    quoted_levels,
    quoted_prices,
)
from app.features.departure.reception import customer_lines
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.services.import_routes import import_mode_labels
from app.features.user.models.user import User
from app.handlers.order import _order_summary


async def _seed(session: AsyncSession) -> dict[str, Any]:
    """An imported article; air (default) and sea on offer, a withdrawn
    « ecologique » route that an old order was paid on."""
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    origin = Place(name="Hub", type="warehouse", is_warehouse=True, country="FR")
    papeete = Place(name="Papeete", type="warehouse", is_warehouse=True, country="PF")
    status = OrderStatus(name=f"Delivered-{uuid.uuid4().hex[:4]}")
    session.add_all([user, origin, papeete, status])
    await session.flush()
    product = Product(
        name="Écran",
        base_price=Decimal("10000"),
        cost_amount=Decimal("10000"),
        cost_currency="XPF",
        weight=2.0,
        customs_rate_pct=Decimal("0"),
        margin_rate_pct=Decimal("0"),
    )
    session.add(product)
    for level, label, per_kg, default, active in (
        ("rapide", "Rapide (avion)", "700", True, True),
        ("economique", "Économique (bateau)", "150", False, True),
        ("ecologique", "Écologique (voilier)", "100", False, False),
    ):
        session.add(
            ShippingRoute(
                from_place_id=origin.id,
                to_place_id=papeete.id,
                name=f"Import {level}",
                mode="air" if default else "sea",
                service_level=level,
                customer_label=label,
                is_default_import=default,
                is_active=active,
                priority=1 if default else 2,
                price_per_kg=Decimal(per_kg),
                route_metadata={"billing_basis": "actual_weight"},
            )
        )
    await session.flush()
    order = Order(
        user_id=user.id,
        order_status_id=status.id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("20000"),
        total_amount=Decimal("20000"),
    )
    session.add(order)
    await session.flush()
    session.add(
        OrderLine(
            order_id=order.id,
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10300"),
            import_service_level="economique",
        )
    )
    ids = {"user_id": user.id, "product_id": product.id, "order_id": order.id}
    await session.commit()
    return ids


@pytest.mark.asyncio
async def test_labels_survive_a_withdrawn_route(db_session: AsyncSession) -> None:
    await _seed(db_session)
    labels = await import_mode_labels(
        db_session, ["economique", "ecologique", "inconnu", None]
    )
    assert labels == {
        "economique": "Économique (bateau)",
        "ecologique": "Écologique (voilier)",  # withdrawn, still named
        "inconnu": "inconnu",  # never blank
    }


@pytest.mark.asyncio
async def test_the_paid_mode_shows_on_admin_customer_and_email(
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session)
    order = await db_session.get(Order, ids["order_id"])
    assert order is not None

    mine = await customer_lines(db_session, order)
    assert mine[0].import_service_level == "economique"
    assert mine[0].import_mode_label == "Économique (bateau)"

    detail = await get_order_detail(ids["order_id"], db_session, object())  # type: ignore[arg-type]
    assert detail.lines[0].import_service_level == "economique"
    assert detail.lines[0].import_mode_label == "Économique (bateau)"

    summary = await _order_summary(db_session, ids["order_id"], "fr")
    assert summary["lines"][0]["import_mode"] == "Économique (bateau)"


@pytest.mark.asyncio
async def test_reorder_keeps_the_paid_mode(db_session: AsyncSession) -> None:
    ids = await _seed(db_session)
    buyer = await db_session.get(User, ids["user_id"])
    assert buyer is not None

    result = await reorder_into_cart(db_session, buyer, ids["order_id"])

    assert result.added == 1
    item = result.cart.items[0]
    assert item.import_service_level == "economique"
    # Priced on sea freight (2 kg × 150), not on the default air route.
    assert item.unit_price == Decimal("10300")


@pytest.mark.asyncio
async def test_reorder_of_a_withdrawn_mode_falls_back_to_the_default(
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session)
    line = (await db_session.exec(_lines_of(ids["order_id"]))).one()
    line.import_service_level = "ecologique"
    db_session.add(line)
    await db_session.commit()
    buyer = await db_session.get(User, ids["user_id"])
    assert buyer is not None

    result = await reorder_into_cart(db_session, buyer, ids["order_id"])

    assert result.cart.items[0].import_service_level == "rapide"


def _lines_of(order_id: uuid.UUID) -> Any:
    from sqlmodel import col, select

    return select(OrderLine).where(col(OrderLine.order_id) == order_id)


@pytest.mark.asyncio
async def test_a_quote_carries_the_mode_back_into_the_cart(
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session)
    product_id = ids["product_id"]
    quote = QuoteRequest(
        email="c@test.local",
        items_snapshot={
            "currency": "XPF",
            "items": [
                {
                    "product_id": str(product_id),
                    "product_name": "Écran",
                    "quantity": "1",
                    "unit_price": "10300",
                    "import_service_level": "economique",
                }
            ],
        },
    )
    # The admin's starting point keeps the requested mode…
    proposed = proposed_lines(quote)
    assert proposed[0].import_service_level == "economique"
    # …the issued quote freezes it…
    quote.quote_snapshot = {
        "lines": [
            {
                "product_id": str(product_id),
                "quantity": 1,
                "unit_price": "9900",
                "import_service_level": "economique",
            }
        ]
    }
    assert quoted_levels(quote) == {product_id: "economique"}
    # …and the accepted quote puts the line back on it, at the quoted price.
    cart = Cart(user_id=ids["user_id"], currency="XPF")
    db_session.add(cart)
    await db_session.flush()
    cart_id = cart.id
    await db_session.commit()
    items = await cart_routes._install_quote_in_cart(
        db_session,
        cart_id=cart_id,
        prices=quoted_prices(quote),
        levels=quoted_levels(quote),
    )
    assert items[0].import_service_level == "economique"
    assert items[0].unit_price == Decimal("9900")
