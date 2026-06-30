"""Integration tests for the admin shipping flows against a real Postgres session.

These are the exact paths that produced a cascade of ``MissingGreenlet`` bugs
(ORM attributes — status defs, tracking rows, the admin user — read after the
per-tracking commit expires them). A mocked session cannot reproduce them; these
real-engine tests would have caught all of them.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_shipping import (
    AdvanceConsolidationRequest,
    ShipRequest,
    advance_consolidation,
    advance_tracking,
    consolidation_ungroup_hint,
    deliver_consolidation,
    deliver_tracking,
    order_journey,
    ship_consolidation,
    ship_tracking,
)
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.place.models import Place
from app.features.shipping.crud.route_tracking import crud_shipping_route_tracking
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingConsolidation,
)
from app.features.shipping.models.status import StatusDefinition
from app.features.user.models.address import Address
from app.features.user.models.user import User
from app.outbox.models import OutboxEvent
from app.tests.integration.factories import seed_shipping_scenario


async def _seed_progression_statuses(session: AsyncSession) -> None:
    """The multi-leg progression vocabulary (in addition to the factory's pending)."""
    session.add_all(
        [
            StatusDefinition(
                entity="route_tracking", code="in_progress", name="En cours"
            ),
            StatusDefinition(entity="route_tracking", code="completed", name="Terminé"),
        ]
    )
    await session.flush()


async def _status_id(session: AsyncSession, *, entity: str, code: str) -> object:
    result = await session.exec(
        select(StatusDefinition).where(
            col(StatusDefinition.entity) == entity,
            col(StatusDefinition.code) == code,
        )
    )
    status = result.first()
    assert status is not None, f"status {entity}/{code} not found"
    return status.id


@pytest.mark.asyncio
async def test_ship_consolidation_advances_all_trackings(
    db_session: AsyncSession,
) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=2)

    response = await ship_consolidation(
        consolidation_id=seed.consolidation_id,
        body=ShipRequest(tracking_ref="CARRIER-XYZ"),
        session=db_session,
        admin=seed.admin,
    )
    assert "2" in response.message

    shipped_id = await _status_id(db_session, entity="route_tracking", code="shipped")
    for tid in seed.tracking_ids:
        tracking = await db_session.get(ShippingRouteTracking, tid)
        assert tracking is not None
        await db_session.refresh(tracking)
        assert tracking.status_id == shipped_id
        assert tracking.tracking_ref == "CARRIER-XYZ"

    # The customer-notification events must be COMMITTED (not just published to a
    # session that never commits) — one per shipped tracking.
    events = await db_session.exec(
        select(OutboxEvent).where(col(OutboxEvent.type) == "tracking.status_changed")
    )
    assert len(events.all()) == len(seed.tracking_ids)


@pytest.mark.asyncio
async def test_ship_single_tracking(db_session: AsyncSession) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=1)
    tid = seed.tracking_ids[0]

    await ship_tracking(
        tracking_id=tid,
        body=ShipRequest(tracking_ref="REF-1"),
        session=db_session,
        admin=seed.admin,
    )

    shipped_id = await _status_id(db_session, entity="route_tracking", code="shipped")
    tracking = await db_session.get(ShippingRouteTracking, tid)
    assert tracking is not None
    await db_session.refresh(tracking)
    assert tracking.status_id == shipped_id
    assert tracking.tracking_ref == "REF-1"


@pytest.mark.asyncio
async def test_activate_next_route_advances_sequence(db_session: AsyncSession) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=2)
    admin_id = seed.admin.id  # capture: the progression commits expire `admin`
    first, second = seed.tracking_ids
    await _seed_progression_statuses(db_session)

    # Leg 1 → leg 2.
    result = await crud_shipping_route_tracking.activate_next_route(
        db_session, current_tracking_id=first, changed_by=admin_id
    )
    assert result is not None
    assert result.id == second

    completed_id = await _status_id(
        db_session, entity="route_tracking", code="completed"
    )
    in_progress_id = await _status_id(
        db_session, entity="route_tracking", code="in_progress"
    )
    t1 = await db_session.get(ShippingRouteTracking, first)
    assert t1 is not None
    await db_session.refresh(t1)
    assert t1.status_id == completed_id

    t2 = await db_session.get(ShippingRouteTracking, second)
    assert t2 is not None
    await db_session.refresh(t2)
    assert t2.status_id == in_progress_id

    # Advancing from the last leg completes it and returns None (no next leg).
    last = await crud_shipping_route_tracking.activate_next_route(
        db_session, current_tracking_id=second, changed_by=admin_id
    )
    assert last is None
    t2_final = await db_session.get(ShippingRouteTracking, second)
    assert t2_final is not None
    await db_session.refresh(t2_final)
    assert t2_final.status_id == completed_id


@pytest.mark.asyncio
async def test_advance_tracking_admin_endpoint(db_session: AsyncSession) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=2)
    first, second = seed.tracking_ids
    await _seed_progression_statuses(db_session)

    resp = await advance_tracking(
        tracking_id=first, session=db_session, admin=seed.admin
    )
    assert resp.has_next is True
    assert resp.next_tracking_id == second

    # Advancing notifies the customer (committed outbox event for the next leg).
    events = await db_session.exec(
        select(OutboxEvent).where(col(OutboxEvent.type) == "tracking.status_changed")
    )
    assert len(events.all()) == 1

    # A real request gets a fresh admin; the previous advance expired this one.
    await db_session.refresh(seed.admin)
    resp_last = await advance_tracking(
        tracking_id=second, session=db_session, admin=seed.admin
    )
    assert resp_last.has_next is False


@pytest.mark.asyncio
async def test_advance_consolidation_admin_endpoint(db_session: AsyncSession) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=2)
    await _seed_progression_statuses(db_session)

    resp = await advance_consolidation(
        consolidation_id=seed.consolidation_id,
        body=AdvanceConsolidationRequest(ungroup=False),
        session=db_session,
        admin=seed.admin,
    )
    assert "colis" in resp.message

    completed_id = await _status_id(
        db_session, entity="route_tracking", code="completed"
    )
    first_leg = await db_session.get(ShippingRouteTracking, seed.tracking_ids[0])
    assert first_leg is not None
    await db_session.refresh(first_leg)
    assert first_leg.status_id == completed_id
    # ungroup=False keeps the parcel attached to the lot.
    assert first_leg.consolidation_id == seed.consolidation_id


@pytest.mark.asyncio
async def test_advance_consolidation_ungroup_detaches(
    db_session: AsyncSession,
) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=2)
    await _seed_progression_statuses(db_session)

    await advance_consolidation(
        consolidation_id=seed.consolidation_id,
        body=AdvanceConsolidationRequest(ungroup=True),
        session=db_session,
        admin=seed.admin,
    )

    # Every parcel is detached from the lot (and advanced individually).
    for tid in seed.tracking_ids:
        tracking = await db_session.get(ShippingRouteTracking, tid)
        assert tracking is not None
        await db_session.refresh(tracking)
        assert tracking.consolidation_id is None


@pytest.mark.asyncio
async def test_deliver_consolidation_detaches_and_delivers(
    db_session: AsyncSession,
) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=2)

    resp = await deliver_consolidation(
        consolidation_id=seed.consolidation_id, session=db_session, admin=seed.admin
    )
    assert "livré" in resp.message

    delivered_id = await _status_id(
        db_session, entity="route_tracking", code="delivered"
    )
    for tid in seed.tracking_ids:
        tracking = await db_session.get(ShippingRouteTracking, tid)
        assert tracking is not None
        await db_session.refresh(tracking)
        assert tracking.consolidation_id is None  # forced ungroup
        assert tracking.status_id == delivered_id  # terminal


@pytest.mark.asyncio
async def test_order_journey(db_session: AsyncSession) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=2)

    legs = await order_journey(
        order_id=seed.order_id, session=db_session, _admin=seed.admin
    )

    assert [leg.sequence_order for leg in legs] == [1, 2]
    assert legs[0].route_name == "FR → PF"
    assert legs[0].from_place == "Métropole"
    assert legs[0].to_place == "Tahiti"
    assert legs[0].mode == "sea"
    assert legs[0].status_code == "pending"
    assert legs[0].is_current is True  # first non-terminal leg
    assert legs[1].is_current is False


@pytest.mark.asyncio
async def test_deliver_single_tracking(db_session: AsyncSession) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=1)
    tid = seed.tracking_ids[0]

    await deliver_tracking(
        tracking_id=tid,
        session=db_session,
        admin=seed.admin,
    )

    delivered_id = await _status_id(
        db_session, entity="route_tracking", code="delivered"
    )
    tracking = await db_session.get(ShippingRouteTracking, tid)
    assert tracking is not None
    await db_session.refresh(tracking)
    assert tracking.status_id == delivered_id


async def _seed_lot_with_next_leg(
    session: AsyncSession, *, next_is_customer: bool
) -> SimpleNamespace:
    """A lot holding one parcel at leg 1, whose leg 2 is either the customer
    last-leg (``is_to_customer``) or a shared intermediate leg."""
    admin = User(
        email=f"a+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    p1 = Place(name="FR", type="warehouse")
    p2 = Place(name="PF", type="warehouse")
    p3 = Place(name="Client", type="address")
    session.add_all([admin, p1, p2, p3])
    await session.flush()

    leg1 = ShippingRoute(
        from_place_id=p1.id, to_place_id=p2.id, name="FR→PF", mode="sea"
    )
    leg2 = ShippingRoute(
        from_place_id=p2.id,
        to_place_id=p3.id,
        name="leg2",
        mode="road",
        is_to_customer=next_is_customer,
    )
    ostatus = OrderStatus(name="Pending")
    st_t = StatusDefinition(entity="route_tracking", code="pending", name="x")
    st_c = StatusDefinition(entity="consolidation", code="pending", name="x")
    session.add_all([leg1, leg2, ostatus, st_t, st_c])
    await session.flush()

    order = Order(
        user_id=admin.id,
        order_status_id=ostatus.id,
        total_amount=Decimal("0"),
        subtotal_amount=Decimal("0"),
        shipping_fee_amount=Decimal("0"),
        payment_fee_amount=Decimal("0"),
        total_fees_amount=Decimal("0"),
    )
    addr = Address(
        user_id=admin.id,
        street="BP 1",
        city="Papeete",
        postal_code="98714",
        country="PF",
        type="shipping",
    )
    session.add_all([order, addr])
    await session.flush()

    cons = ShippingRouteTrackingConsolidation(
        route_id=leg1.id,
        name="Lot",
        consolidation_code=f"CONS-{uuid.uuid4().hex[:8].upper()}",
        status_id=st_c.id,
        total_orders=1,
    )
    session.add(cons)
    await session.flush()

    now = datetime.now(timezone.utc)
    session.add_all(
        [
            ShippingRouteTracking(
                order_id=order.id,
                route_id=leg1.id,
                status_id=st_t.id,
                address_id=addr.id,
                consolidation_id=cons.id,
                sequence_order=1,
                selected_at=now,
            ),
            ShippingRouteTracking(
                order_id=order.id,
                route_id=leg2.id,
                status_id=st_t.id,
                address_id=addr.id,
                sequence_order=2,
                selected_at=now,
            ),
        ]
    )
    await session.flush()
    return SimpleNamespace(admin=admin, consolidation_id=cons.id)


@pytest.mark.asyncio
async def test_ungroup_hint_true_when_next_leg_is_customer(
    db_session: AsyncSession,
) -> None:
    seed = await _seed_lot_with_next_leg(db_session, next_is_customer=True)
    resp = await consolidation_ungroup_hint(
        consolidation_id=seed.consolidation_id, session=db_session, _admin=seed.admin
    )
    assert resp.suggest_ungroup is True


@pytest.mark.asyncio
async def test_ungroup_hint_false_when_next_leg_is_shared(
    db_session: AsyncSession,
) -> None:
    seed = await _seed_lot_with_next_leg(db_session, next_is_customer=False)
    resp = await consolidation_ungroup_hint(
        consolidation_id=seed.consolidation_id, session=db_session, _admin=seed.admin
    )
    assert resp.suggest_ungroup is False
