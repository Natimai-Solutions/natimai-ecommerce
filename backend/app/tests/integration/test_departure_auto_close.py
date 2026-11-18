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


@pytest.mark.asyncio
async def test_a_departure_left_open_does_not_call_the_supplier_every_tick(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of 17/11/2026: the live stock check ran before the threshold
    test — every 15 minutes, one supplier API call per product, for a
    departure that then stayed open anyway."""
    from unittest.mock import AsyncMock

    from app.features.departure import services as departure_services

    shortages = AsyncMock(return_value=[])
    monkeypatch.setattr(departure_services, "find_shortages", shortages)
    now = datetime.now(UTC)
    db_session.add_all(
        [
            GroupedDeparture(
                name="Bateau",
                order_cutoff_at=now - timedelta(minutes=5),
                status="open",
                is_published=True,
                min_amount=Decimal("1000000"),
            ),
            GroupedDeparture(
                name="Avion",
                order_cutoff_at=now - timedelta(minutes=5),
                status="open",
                is_published=True,
            ),
        ]
    )
    await db_session.commit()

    result = await close_due_departures(db_session, now=now)

    assert result == {"closed": ["Avion"], "below_threshold": ["Bateau"]}
    # Asked once, for the departure that closed — not for the one left open.
    assert shortages.await_count == 1


@pytest.mark.asyncio
async def test_the_status_page_shows_a_departure_waiting_past_its_cutoff(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of 17/11/2026: a departure stuck below its threshold was told
    once a week by webhook, and « État du système » said all is well."""
    from unittest.mock import AsyncMock

    from app.api.routes import admin_system_status

    monkeypatch.setattr(
        admin_system_status, "module_enabled", AsyncMock(return_value=True)
    )
    now = datetime.now(UTC)
    db_session.add_all(
        [
            GroupedDeparture(
                name="Bateau",
                order_cutoff_at=now - timedelta(hours=30),
                status="open",
                is_published=True,
                min_amount=Decimal("1000000"),
            ),
            GroupedDeparture(
                name="Plus tard",
                order_cutoff_at=now + timedelta(days=3),
                status="open",
                is_published=True,
            ),
        ]
    )
    await db_session.commit()

    status = await admin_system_status.get_system_status(db_session, object())  # type: ignore[arg-type]

    assert [d.name for d in status.departures_waiting] == ["Bateau"]
    assert status.departures_waiting[0].hours_past_cutoff == 30
    assert status.departures_level == "warn"
    assert status.level in ("warn", "error")
