"""Integration test for the logistics status/transition seed (harmonization)."""

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.initial_data import _seed_shipping_statuses
from app.features.shipping.crud.route_tracking import crud_shipping_route_tracking
from app.features.shipping.models.status import StatusDefinition, StatusTransition


@pytest.mark.asyncio
async def test_seed_shipping_statuses_idempotent_and_validates(
    db_session: AsyncSession,
) -> None:
    # Run twice: the second pass must not create duplicates.
    await _seed_shipping_statuses(db_session)
    await _seed_shipping_statuses(db_session)
    await db_session.flush()

    definitions = list((await db_session.exec(select(StatusDefinition))).all())
    route_codes = {d.code for d in definitions if d.entity == "route_tracking"}
    consol_codes = {d.code for d in definitions if d.entity == "consolidation"}
    assert route_codes == {
        "pending",
        "in_progress",
        "shipped",
        "completed",
        "delivered",
    }
    assert consol_codes == {"pending", "shipped", "delivered"}

    transitions = list((await db_session.exec(select(StatusTransition))).all())
    assert len(transitions) == 9

    # A seeded transition is allowed; an unseeded one is rejected — this is what
    # makes the force=False /update-status route usable.
    allowed = await crud_shipping_route_tracking.validate_status_transition(
        session=db_session,
        current_status="pending",
        new_status="in_progress",
        entity="route_tracking",
    )
    rejected = await crud_shipping_route_tracking.validate_status_transition(
        session=db_session,
        current_status="pending",
        new_status="delivered",
        entity="route_tracking",
    )
    assert allowed is True
    assert rejected is False
