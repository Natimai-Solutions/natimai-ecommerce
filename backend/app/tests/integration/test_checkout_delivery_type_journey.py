"""Integration tests: the checkout journey is driven by ``delivery_type``.

Regression guard for the double last-leg bug: the storefront used to send
``shipping_preference=fastest`` on top of ``delivery_type``; the checkout then
auto-picked the fastest customer route AND appended the chosen one — billing
two last legs and tracking the wrong carrier whenever they differed.

Target behaviour, from a one-warehouse shop to supplier-sourced orders:
- the chosen last leg is the ONLY customer leg (priced once, tracked once);
- goods in local stock need no upstream leg;
- supplier goods get their supplier → main warehouse legs first.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import (
    FulfillmentSegment,
    _link_fulfillment_segments_to_tracking,
    _select_checkout_routes_by_preference,
)
from app.features.cart.models.cart import CheckoutShippingPreference
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.place.models import Place
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_tracking import ShippingRouteTracking
from app.features.user.models.user import User


async def _seed_shop(session: AsyncSession) -> SimpleNamespace:
    """A classic shop: one warehouse, two carriers to the customer, one supplier."""
    user = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        is_superuser=False,
        hashed_password="x",
    )
    warehouse = Place(name="Entrepôt", type="warehouse", is_warehouse=True)
    customer = Place(name="Client", type="address")
    supplier = Place(name="Fournisseur", type="supplier")
    session.add_all([user, warehouse, customer, supplier])
    await session.flush()

    express = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Chronopost express",
        mode="road",
        is_to_customer=True,
        last_leg_delivery_type="express",
        eta_days=1,
        priority=1,
        base_price=Decimal("15.00"),
    )
    standard = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Colissimo domicile",
        mode="road",
        is_to_customer=True,
        last_leg_delivery_type="home_delivery",
        eta_days=3,
        priority=2,
        base_price=Decimal("6.00"),
    )
    inbound = ShippingRoute(
        from_place_id=supplier.id,
        to_place_id=warehouse.id,
        name="Fournisseur → entrepôt",
        mode="road",
        is_to_customer=False,
        eta_days=2,
    )
    order_status = OrderStatus(name="Pending")
    session.add_all([express, standard, inbound, order_status])
    await session.flush()

    order = Order(
        user_id=user.id,
        order_status_id=order_status.id,
        total_amount=Decimal("0"),
        subtotal_amount=Decimal("0"),
        shipping_fee_amount=Decimal("0"),
        payment_fee_amount=Decimal("0"),
        total_fees_amount=Decimal("0"),
    )
    session.add(order)
    await session.flush()

    return SimpleNamespace(
        user=user,
        warehouse_id=warehouse.id,
        supplier_id=supplier.id,
        express=express,
        standard=standard,
        inbound=inbound,
        order_id=order.id,
    )


async def _journey(
    session: AsyncSession, order_id: uuid.UUID
) -> list[tuple[int, uuid.UUID, uuid.UUID | None]]:
    """(sequence, route_id, consolidation_id) of the order's legs, in order."""
    result = await session.exec(
        select(ShippingRouteTracking)
        .where(ShippingRouteTracking.order_id == order_id)
        .order_by(col(ShippingRouteTracking.sequence_order).asc())
    )
    return [(t.sequence_order, t.route_id, t.consolidation_id) for t in result.all()]


@pytest.mark.asyncio
async def test_preference_never_adds_a_second_last_leg(
    db_session: AsyncSession,
) -> None:
    shop = await _seed_shop(db_session)

    # With a delivery_type in the checkout, the preference must leave the
    # customer routes alone: only the upstream (non-customer) leg is picked.
    selected = await _select_checkout_routes_by_preference(
        session=db_session,
        preference=CheckoutShippingPreference.FASTEST,
        total_weight_kg=Decimal("1"),
        declared_value=Decimal("100"),
        currency="EUR",
        destination_chain=[],
        include_customer_routes=False,
    )
    assert [r.id for r in selected] == [shop.inbound.id]
    assert not any(r.is_to_customer for r in selected)

    # Legacy callers without delivery_type keep the fastest customer route.
    legacy = await _select_checkout_routes_by_preference(
        session=db_session,
        preference=CheckoutShippingPreference.FASTEST,
        total_weight_kg=Decimal("1"),
        declared_value=Decimal("100"),
        currency="EUR",
        destination_chain=[],
    )
    assert [r.id for r in legacy] == [shop.inbound.id, shop.express.id]


@pytest.mark.asyncio
async def test_local_stock_gets_one_leg_on_the_chosen_carrier(
    db_session: AsyncSession,
) -> None:
    shop = await _seed_shop(db_session)

    # The customer picked the slower carrier: it must be the ONLY leg, not the
    # "fastest" one the heuristic would have chosen.
    await _link_fulfillment_segments_to_tracking(
        session=db_session,
        order_id=shop.order_id,
        current_user=shop.user,
        shipping_address="1 rue de la Paix, Paris, FR",
        segment_totals={(FulfillmentSegment.LOCAL, shop.warehouse_id): Decimal("2")},
        last_leg_route=shop.standard,
    )

    assert await _journey(db_session, shop.order_id) == [(1, shop.standard.id, None)]


@pytest.mark.asyncio
async def test_supplier_goods_travel_to_warehouse_then_to_customer(
    db_session: AsyncSession,
) -> None:
    shop = await _seed_shop(db_session)

    await _link_fulfillment_segments_to_tracking(
        session=db_session,
        order_id=shop.order_id,
        current_user=shop.user,
        shipping_address="1 rue de la Paix, Paris, FR",
        segment_totals={
            (FulfillmentSegment.LOCAL, shop.warehouse_id): Decimal("1"),
            (FulfillmentSegment.VIA_MAIN_WAREHOUSE, shop.supplier_id): Decimal("1"),
        },
        last_leg_route=shop.standard,
    )

    journey = await _journey(db_session, shop.order_id)
    assert [(seq, route) for seq, route, _ in journey] == [
        (1, shop.inbound.id),
        (2, shop.standard.id),
    ]
    # Regrouped at the warehouse: the inbound leg carries a lot, the last leg none.
    assert journey[0][2] is not None
    assert journey[1][2] is None


@pytest.mark.asyncio
async def test_dropship_goods_go_straight_from_supplier_to_customer(
    db_session: AsyncSession,
) -> None:
    shop = await _seed_shop(db_session)

    # A dropshipping supplier with no customer route of its own: the parcel
    # travels on the delivery mode the customer chose — as the ONLY leg.
    await _link_fulfillment_segments_to_tracking(
        session=db_session,
        order_id=shop.order_id,
        current_user=shop.user,
        shipping_address="1 rue de la Paix, Paris, FR",
        segment_totals={
            (FulfillmentSegment.SUPPLIER_DIRECT, shop.supplier_id): Decimal("1"),
        },
        last_leg_route=shop.express,
    )
    assert await _journey(db_session, shop.order_id) == [(1, shop.express.id, None)]


@pytest.mark.asyncio
async def test_dropship_uses_the_supplier_customer_route_when_configured(
    db_session: AsyncSession,
) -> None:
    shop = await _seed_shop(db_session)
    customer_place_id = shop.express.to_place_id
    direct = ShippingRoute(
        from_place_id=shop.supplier_id,
        to_place_id=customer_place_id,
        name="Fournisseur → client (dropship)",
        mode="road",
        is_to_customer=True,
    )
    db_session.add(direct)
    await db_session.flush()
    direct_id = direct.id

    # Mixed order: local stock takes the chosen carrier, the dropshipped item
    # its supplier's own route — two parallel final legs, no warehouse hop.
    await _link_fulfillment_segments_to_tracking(
        session=db_session,
        order_id=shop.order_id,
        current_user=shop.user,
        shipping_address="1 rue de la Paix, Paris, FR",
        segment_totals={
            (FulfillmentSegment.LOCAL, shop.warehouse_id): Decimal("1"),
            (FulfillmentSegment.SUPPLIER_DIRECT, shop.supplier_id): Decimal("1"),
        },
        last_leg_route=shop.standard,
    )
    assert await _journey(db_session, shop.order_id) == [
        (1, direct_id, None),
        (2, shop.standard.id, None),
    ]


@pytest.mark.asyncio
async def test_consolidated_supplier_goods_keep_their_lot_upstream_only(
    db_session: AsyncSession,
) -> None:
    shop = await _seed_shop(db_session)

    await _link_fulfillment_segments_to_tracking(
        session=db_session,
        order_id=shop.order_id,
        current_user=shop.user,
        shipping_address="BP 1, Papeete, PF",
        segment_totals={
            (FulfillmentSegment.VIA_MAIN_WAREHOUSE, shop.supplier_id): Decimal("1"),
        },
        last_leg_route=shop.express,
    )

    journey = await _journey(db_session, shop.order_id)
    assert [(seq, route) for seq, route, _ in journey] == [
        (1, shop.inbound.id),
        (2, shop.express.id),
    ]
    # The lot groups the inbound leg; the customer leg is never consolidated.
    assert journey[0][2] is not None
    assert journey[1][2] is None


@pytest.mark.asyncio
async def test_without_delivery_type_legacy_heuristic_is_unchanged(
    db_session: AsyncSession,
) -> None:
    shop = await _seed_shop(db_session)

    await _link_fulfillment_segments_to_tracking(
        session=db_session,
        order_id=shop.order_id,
        current_user=shop.user,
        shipping_address="1 rue de la Paix, Paris, FR",
        segment_totals={(FulfillmentSegment.LOCAL, shop.warehouse_id): Decimal("2")},
    )

    # Legacy: the first customer route by priority.
    assert await _journey(db_session, shop.order_id) == [(1, shop.express.id, None)]
