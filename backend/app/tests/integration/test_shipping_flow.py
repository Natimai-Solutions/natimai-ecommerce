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
    deliver_tracking,
    ship_consolidation,
    ship_tracking,
)
from app.features.shipping.models.route_tracking import ShippingRouteTracking
from app.features.shipping.models.status import StatusDefinition
from app.tests.integration.factories import seed_shipping_scenario


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
