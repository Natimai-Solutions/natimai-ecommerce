"""Integration (real DB): a visitor sees the delivery price to their island
before signing in — only the modes serving that island, priced for their
cart."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import estimate_product_shipping, get_guest_last_leg_options
from app.features.cart.models.cart import Cart, CartItem
from app.features.place.models import Place
from app.features.product.models.product import PricingMode, Product
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_served_place import RouteServedPlace

TOKEN = "guest-token-0123456789abcdef"


@pytest.mark.asyncio
async def test_the_estimate_lists_the_modes_serving_the_island(
    db_session: AsyncSession,
) -> None:
    country = Place(name="Polynésie", type="country")
    db_session.add(country)
    await db_session.flush()
    archipelago = Place(name="Îles du Vent", type="archipelago", parent_id=country.id)
    db_session.add(archipelago)
    await db_session.flush()
    moorea = Place(name="Moorea", type="island", parent_id=archipelago.id)
    bora = Place(name="Bora Bora", type="island", parent_id=country.id)
    warehouse = Place(name="Entrepôt", type="warehouse", is_warehouse=True)
    db_session.add_all([moorea, bora, warehouse])
    await db_session.flush()

    ferry = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=moorea.id,
        name="Ferry Moorea",
        mode="sea",
        is_to_customer=True,
        last_leg_delivery_type="ferry",
        base_price=Decimal("500"),
        price_per_kg=Decimal("100"),
    )
    plane = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=bora.id,
        name="Avion Bora",
        mode="air",
        is_to_customer=True,
        last_leg_delivery_type="air",
        base_price=Decimal("2000"),
        price_per_kg=Decimal("300"),
    )
    db_session.add_all([ferry, plane])
    await db_session.flush()
    db_session.add_all(
        [
            RouteServedPlace(route_id=ferry.id, place_id=archipelago.id),
            RouteServedPlace(route_id=plane.id, place_id=bora.id),
        ]
    )
    product = Product(
        name="Écran",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("25000"),
        weight=2.0,
        supplier_name="shop",
        supplier_sku=f"s-{uuid.uuid4().hex[:6]}",
    )
    cart = Cart(guest_token=TOKEN, user_id=None, currency="XPF")
    db_session.add_all([product, cart])
    await db_session.flush()
    db_session.add(
        CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("25000"),
        )
    )
    moorea_id, bora_id, product_id = moorea.id, bora.id, product.id
    await db_session.commit()

    to_moorea = await get_guest_last_leg_options(db_session, TOKEN, place_id=moorea_id)
    to_bora = await get_guest_last_leg_options(db_session, TOKEN, place_id=bora_id)

    # Moorea is served through its archipelago, by the ferry only.
    assert [o.delivery_type for o in to_moorea.options] == ["ferry"]
    assert to_moorea.options[0].amount == Decimal("700")  # 500 + 100 × 2 kg
    assert [o.delivery_type for o in to_bora.options] == ["air"]

    # No cart, no estimate (and no error).
    empty = await get_guest_last_leg_options(
        db_session, "another-token-0123456789", place_id=moorea_id
    )
    assert empty.options == []

    # From the product page, before anything is in a cart.
    two = await estimate_product_shipping(
        db_session, product_id, place_id=moorea_id, quantity=2
    )
    assert [(o.delivery_type, o.amount) for o in two.options] == [
        ("ferry", Decimal("900"))  # 500 + 100 × 4 kg
    ]
