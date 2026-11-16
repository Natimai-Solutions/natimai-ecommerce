"""Integration (real DB): a departure past its cut-off closes on its own
when its threshold is reached (functional audit, November 2026: only the
admin closed it, and until then new orders were attached to no departure)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.departure.models import GroupedDeparture
from app.features.departure.services import close_due_departures


@pytest.mark.asyncio
async def test_departures_past_their_cutoff_close_or_wait(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    no_threshold = GroupedDeparture(
        name="Avion hebdo",
        order_cutoff_at=now - timedelta(minutes=5),
        status="open",
        is_published=True,
        recurrence_days=7,
    )
    below = GroupedDeparture(
        name="Bateau",
        order_cutoff_at=now - timedelta(minutes=5),
        status="open",
        is_published=True,
        min_amount=Decimal("1000000"),
    )
    future = GroupedDeparture(
        name="Plus tard",
        order_cutoff_at=now + timedelta(days=3),
        status="open",
        is_published=True,
    )
    db_session.add_all([no_threshold, below, future])
    await db_session.commit()

    result = await close_due_departures(db_session, now=now)

    assert result == {"closed": ["Avion hebdo"], "below_threshold": ["Bateau"]}
    statuses = {
        d.name: d.status
        for d in (await db_session.exec(select(GroupedDeparture))).all()
    }
    assert statuses["Avion hebdo"] == "closed"
    assert statuses["Bateau"] == "open"  # the admin decides
    assert statuses["Plus tard"] == "open"
    # The recurring one opened its next departure, a week later.
    following = (
        await db_session.exec(
            select(GroupedDeparture).where(
                col(GroupedDeparture.name) == "Avion hebdo (suivant)"
            )
        )
    ).one()
    assert following.status == "open" and following.order_cutoff_at > now
