"""Integration tests for the admin shipping flows against a real Postgres session.

These are the exact paths that produced a cascade of ``MissingGreenlet`` bugs
(ORM attributes — status defs, tracking rows, the admin user — read after the
per-tracking commit expires them). A mocked session cannot reproduce them; these
real-engine tests would have caught all of them.
"""

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_shipping import (
    ShipRequest,
    advance_consolidation,
    advance_tracking,
    deliver_tracking,
    ship_consolidation,
    ship_tracking,
)
from app.features.shipping.crud.route_tracking import crud_shipping_route_tracking
from app.features.shipping.models.route_tracking import ShippingRouteTracking
from app.features.shipping.models.status import StatusDefinition
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
        consolidation_id=seed.consolidation_id, session=db_session, admin=seed.admin
    )
    assert "colis" in resp.message

    completed_id = await _status_id(
        db_session, entity="route_tracking", code="completed"
    )
    first_leg = await db_session.get(ShippingRouteTracking, seed.tracking_ids[0])
    assert first_leg is not None
    await db_session.refresh(first_leg)
    assert first_leg.status_id == completed_id


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
