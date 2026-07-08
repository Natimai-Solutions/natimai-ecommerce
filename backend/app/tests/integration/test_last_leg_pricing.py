"""Integration tests: last-leg (zone C) route resolution and tariff.

Covers the item-5 wiring: the checkout resolves a last-leg route from the
customer's ``delivery_type`` and prices it (base_price + price_per_kg × weight).
The resolved route + this tariff are what get added to the order total.
"""

from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import _resolve_last_leg_route
from app.features.place.models import Place
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.services.pricing import calculate_shipping_for_routes


async def _seed_warehouse_and_customer(session: AsyncSession) -> tuple[Place, Place]:
    warehouse = Place(name="Entrepôt Papeete", type="warehouse", is_warehouse=True)
    customer = Place(name="Zone client", type="address")
    session.add_all([warehouse, customer])
    await session.flush()
    return warehouse, customer


@pytest.mark.asyncio
async def test_resolve_last_leg_route_matches_delivery_type(
    db_session: AsyncSession,
) -> None:
    warehouse, customer = await _seed_warehouse_and_customer(db_session)
    home = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Livraison domicile",
        mode="road",
        is_to_customer=True,
        last_leg_delivery_type="home_delivery",
    )
    air = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Fret aérien archipels",
        mode="air",
        is_to_customer=True,
        last_leg_delivery_type="air_freight",
    )
    db_session.add_all([home, air])
    await db_session.flush()
    home_id, air_id = home.id, air.id

    resolved_home = await _resolve_last_leg_route(
        db_session, delivery_type="home_delivery"
    )
    resolved_air = await _resolve_last_leg_route(
        db_session, delivery_type="air_freight"
    )
    assert resolved_home is not None and resolved_home.id == home_id
    assert resolved_air is not None and resolved_air.id == air_id


@pytest.mark.asyncio
async def test_resolve_last_leg_route_none_when_untyped_or_missing(
    db_session: AsyncSession,
) -> None:
    warehouse, customer = await _seed_warehouse_and_customer(db_session)
    # A to-customer route WITHOUT a delivery-type tag must not be matched.
    db_session.add(
        ShippingRoute(
            from_place_id=warehouse.id,
            to_place_id=customer.id,
            name="Non taggée",
            mode="road",
            is_to_customer=True,
            last_leg_delivery_type=None,
        )
    )
    await db_session.flush()

    assert await _resolve_last_leg_route(db_session, delivery_type=None) is None
    assert (
        await _resolve_last_leg_route(db_session, delivery_type="home_delivery") is None
    )


@pytest.mark.asyncio
async def test_resolve_last_leg_route_prefers_lowest_priority(
    db_session: AsyncSession,
) -> None:
    warehouse, customer = await _seed_warehouse_and_customer(db_session)
    high = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Domicile (secondaire)",
        mode="road",
        is_to_customer=True,
        last_leg_delivery_type="home_delivery",
        priority=10,
    )
    low = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Domicile (principale)",
        mode="road",
        is_to_customer=True,
        last_leg_delivery_type="home_delivery",
        priority=1,
    )
    db_session.add_all([high, low])
    await db_session.flush()
    low_id = low.id

    resolved = await _resolve_last_leg_route(db_session, delivery_type="home_delivery")
    assert resolved is not None and resolved.id == low_id


@pytest.mark.asyncio
async def test_last_leg_tariff_is_base_plus_per_kg(db_session: AsyncSession) -> None:
    warehouse, customer = await _seed_warehouse_and_customer(db_session)
    route = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Domicile tarifé",
        mode="road",
        is_to_customer=True,
        last_leg_delivery_type="home_delivery",
        base_price=Decimal("500"),
        price_per_kg=Decimal("100"),
    )
    db_session.add(route)
    await db_session.flush()

    # 500 (forfait) + 100 × 2 kg = 700 — exactly what checkout folds into the total.
    summary = calculate_shipping_for_routes(
        routes=[route],
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("10000"),
        currency="XPF",
    )
    assert summary.total_fee == Decimal("700")


@pytest.mark.asyncio
async def test_resolve_custom_delivery_mode(db_session: AsyncSession) -> None:
    # Modes are free-form: a route tagged with an arbitrary mode is resolvable —
    # the admin can add e.g. "sea_freight" without any code change.
    warehouse, customer = await _seed_warehouse_and_customer(db_session)
    route = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Fret bateau",
        mode="sea",
        is_to_customer=True,
        last_leg_delivery_type="sea_freight",
    )
    db_session.add(route)
    await db_session.flush()
    route_id = route.id

    resolved = await _resolve_last_leg_route(db_session, delivery_type="sea_freight")
    assert resolved is not None and resolved.id == route_id
