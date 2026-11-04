"""Rules fixed after the help-panel review.

- A draft or open departure is closed only through the assisted close
  (thresholds, live stock, recurrence): a bare status change is refused.
- A closed departure stays published: its customers keep following it.
- « Garder le groupage » keeps a lot together on its next leg when the next
  legs share a route.

The DB is mocked: only the decision logic is under test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes import admin_grouped_departures as departures_routes
from app.api.routes import admin_shipping as shipping_routes
from app.core.errors import AppError
from app.features.departure import services as departure_services
from app.features.departure.crud import crud_grouped_departure
from app.features.departure.models import GroupedDeparture, GroupedDepartureUpdate
from app.features.shipping.crud import crud_shipping_route_tracking_consolidation


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["draft", "open"])
async def test_bare_close_of_an_open_departure_is_refused(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    monkeypatch.setattr(
        departures_routes,
        "_get_or_404",
        AsyncMock(return_value=SimpleNamespace(status=status)),
    )
    update = AsyncMock()
    monkeypatch.setattr(crud_grouped_departure, "update", update)

    with pytest.raises(AppError) as refused:
        await departures_routes.update_departure(
            uuid.uuid4(),
            GroupedDepartureUpdate(status="closed"),
            cast(Any, MagicMock()),
            cast(Any, SimpleNamespace(id=uuid.uuid4())),
        )

    assert refused.value.code == "grouped_departure.close_required"
    assert refused.value.status_code == 409
    update.assert_not_awaited()


@pytest.mark.anyio
async def test_assisted_close_keeps_the_departure_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        departure_services, "_attached_orders", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        departure_services, "find_shortages", AsyncMock(return_value=[])
    )
    departure = GroupedDeparture(
        name="Octobre",
        order_cutoff_at=datetime.now(UTC) + timedelta(days=3),
        status="open",
        is_published=True,
    )
    session = MagicMock()

    result = await departure_services.close_departure(session, departure=departure)

    assert result.closed
    assert departure.status == "closed"
    assert departure.is_published is True


@pytest.mark.anyio
async def test_kept_lot_is_regrouped_on_the_common_next_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    next_route = uuid.uuid4()
    lot = SimpleNamespace(id=uuid.uuid4(), consolidation_code="CONS-NEXT0001")
    new_lot = AsyncMock(return_value=(lot, None))
    monkeypatch.setattr(shipping_routes, "_new_consolidation", new_lot)
    attach = AsyncMock(return_value=True)
    monkeypatch.setattr(
        crud_shipping_route_tracking_consolidation,
        "add_tracking_to_consolidation",
        attach,
    )
    legs = [(uuid.uuid4(), next_route), (uuid.uuid4(), next_route)]

    code = await shipping_routes._regroup_next_legs(
        cast(Any, MagicMock()), next_legs=legs, name="Lot Papeete", notes=None
    )

    assert code == "CONS-NEXT0001"
    assert new_lot.await_args is not None
    assert new_lot.await_args.kwargs["route_id"] == next_route
    assert {c.kwargs["tracking_id"] for c in attach.await_args_list} == {
        leg for leg, _ in legs
    }
    assert {c.kwargs["consolidation_id"] for c in attach.await_args_list} == {lot.id}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "legs",
    [
        [],
        [(uuid.uuid4(), uuid.uuid4()), (uuid.uuid4(), uuid.uuid4())],
    ],
    ids=["nothing to group", "different next routes"],
)
async def test_no_regrouping_without_a_common_next_route(
    monkeypatch: pytest.MonkeyPatch, legs: list[tuple[uuid.UUID, uuid.UUID]]
) -> None:
    new_lot = AsyncMock()
    monkeypatch.setattr(shipping_routes, "_new_consolidation", new_lot)

    code = await shipping_routes._regroup_next_legs(
        cast(Any, MagicMock()), next_legs=legs, name="Lot", notes=None
    )

    assert code is None
    new_lot.assert_not_awaited()
