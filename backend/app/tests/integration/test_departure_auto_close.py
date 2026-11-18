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


@pytest.mark.asyncio
async def test_a_recurring_departure_below_its_threshold_opens_the_next_one(
    db_session: AsyncSession,
) -> None:
    """Decision of 18/11/2026 (option B): a departure left open below its
    threshold past its cut-off received no more orders and none other was
    open — the new orders were attached to no departure. The following one
    of a recurring departure opens in advance; closing the late one later
    does not open a second."""
    from app.features.departure.crud import crud_grouped_departure
    from app.features.departure.services import close_departure

    now = datetime.now(UTC)
    late = GroupedDeparture(
        name="Avion décembre",
        order_cutoff_at=now - timedelta(hours=2),
        status="open",
        is_published=True,
        min_amount=Decimal("500000"),
        recurrence_days=30,
    )
    db_session.add(late)
    await db_session.flush()
    late_id = late.id
    await db_session.commit()

    result = await close_due_departures(db_session, now=now)
    assert result["below_threshold"] == ["Avion décembre"]

    waiting = await db_session.get(GroupedDeparture, late_id)
    assert waiting is not None and waiting.status == "open"
    assert waiting.next_departure_id is not None
    following = await crud_grouped_departure.get_next_open(db_session, now=now)
    assert following is not None and following.id == waiting.next_departure_id
    assert following.order_cutoff_at > now
    following_id = following.id

    # Next ticks and the forced close reuse it.
    await close_due_departures(db_session, now=now)
    to_close = await db_session.get(GroupedDeparture, late_id)
    assert to_close is not None
    closed = await close_departure(db_session, departure=to_close, force=True)
    await db_session.commit()
    assert closed.closed and closed.next_departure_id == following_id
    successors = (
        await db_session.exec(
            select(GroupedDeparture).where(
                col(GroupedDeparture.name) == "Avion décembre (suivant)"
            )
        )
    ).all()
    assert len(successors) == 1


@pytest.mark.asyncio
async def test_an_order_goes_to_the_next_departure_of_its_mode(
    db_session: AsyncSession,
) -> None:
    """Functional audit D1: a departure carried no mode, so an order paid by
    sea went with the next air departure and showed its date."""
    from app.features.departure.crud import crud_grouped_departure

    now = datetime.now(UTC)
    db_session.add_all(
        [
            GroupedDeparture(
                name="Avion",
                order_cutoff_at=now + timedelta(days=2),
                status="open",
                is_published=True,
                service_level="rapide",
            ),
            GroupedDeparture(
                name="Bateau",
                order_cutoff_at=now + timedelta(days=10),
                status="open",
                is_published=True,
                service_level="economique",
            ),
            GroupedDeparture(
                name="Tous modes",
                order_cutoff_at=now + timedelta(days=5),
                status="open",
                is_published=True,
            ),
        ]
    )
    await db_session.commit()

    async def name_for(level: str | None) -> str | None:
        found = await crud_grouped_departure.get_next_open(
            db_session, now=now, service_level=level
        )
        return found.name if found else None

    assert await name_for("economique") == "Bateau"
    assert await name_for("rapide") == "Avion"
    # A mode with no departure of its own: one carrying no mode.
    assert await name_for("ecologique") == "Tous modes"
    # No mode asked: the nearest, as before.
    assert await name_for(None) == "Avion"
