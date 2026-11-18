"""Integration (real DB): what the « commande reçue » e-mail says.

Review of 17/11/2026: the product names stayed in French in an English
e-mail, the estimated date was printed in UTC (a day early every afternoon
at Tahiti), and a pickup order showed the customer's own address as if the
parcel were delivered there."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.departure.models import GroupedDeparture
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.features.shipping.models.route import ShippingRoute
from app.features.user.models.user import User
from app.handlers.order import _order_summary


async def _order(session: AsyncSession, *, pickup: bool) -> uuid.UUID:
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    status = OrderStatus(name=f"Pending-{uuid.uuid4().hex[:4]}")
    shop = Place(
        name="Boutique Fare Ute",
        type="warehouse",
        is_warehouse=True,
        address_line1="12 rue du Port",
        postal_code="98714",
        city="Papeete",
    )
    product = Product(
        name="Clavier sans fil",
        base_price=Decimal("8000"),
        translations={"en": {"name": "Wireless keyboard"}},
    )
    session.add_all([user, status, shop, product])
    await session.flush()
    counter = ShippingRoute(
        from_place_id=shop.id,
        to_place_id=shop.id,
        name="Retrait boutique",
        mode="pickup",
        is_to_customer=True,
        last_leg_delivery_type="click_collect",
    )
    departure = GroupedDeparture(
        name="Avion décembre",
        order_cutoff_at=datetime(2026, 12, 1, tzinfo=UTC),
        # 05:00 UTC on the 10th is the evening of the 9th at Tahiti.
        estimated_delivery_at=datetime(2026, 12, 10, 5, 0, tzinfo=UTC),
        status="open",
    )
    session.add_all([counter, departure])
    await session.flush()
    order = Order(
        user_id=user.id,
        order_status_id=status.id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("8000"),
        total_amount=Decimal("8000"),
        shipping_address="Jean Dupont, 4 allée des Tiare, 98713 Papeete",
        delivery_type="click_collect" if pickup else "home_delivery",
        grouped_departure_id=departure.id,
        shipping_cost_breakdown=(
            {"segments": [{"route_id": str(counter.id)}]} if pickup else None
        ),
    )
    session.add(order)
    await session.flush()
    session.add(
        OrderLine(
            order_id=order.id,
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("8000"),
        )
    )
    order_id = order.id
    await session.commit()
    return order_id


@pytest.fixture
def _tahiti(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SHOP_TIMEZONE", "Pacific/Tahiti")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_tahiti")
async def test_names_in_the_customer_language_and_date_on_the_shop_clock(
    db_session: AsyncSession,
) -> None:
    order_id = await _order(db_session, pickup=False)

    english: dict[str, Any] = await _order_summary(db_session, order_id, "en")
    french: dict[str, Any] = await _order_summary(db_session, order_id, "fr")

    assert english["lines"][0]["name"] == "Wireless keyboard"
    assert french["lines"][0]["name"] == "Clavier sans fil"
    assert french["estimated_delivery"] == "09/12/2026"
    assert english["estimated_delivery"] == "09 Dec 2026"
    # Delivered: the customer's address, no pickup place.
    assert french["shipping_address"].startswith("Jean Dupont")
    assert french["pickup_place"] == ""


@pytest.mark.asyncio
async def test_a_pickup_shows_where_to_collect_not_the_customer_address(
    db_session: AsyncSession,
) -> None:
    order_id = await _order(db_session, pickup=True)

    summary = await _order_summary(db_session, order_id, "fr")

    assert summary["shipping_address"] == ""
    assert summary["pickup_place"] == "Boutique Fare Ute, 12 rue du Port, 98714 Papeete"
