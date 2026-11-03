"""Several pickup points for one « Retrait » delivery mode.

Pickup routes are grouped by delivery mode *and* pickup place: each point is
its own offer at checkout, the customer picks one (``pickup_place_id``). Other
modes keep one offer per mode, the most specific zone then priority winning.
The DB is mocked: the first ``exec`` yields the routes, the second their
served zones.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes import cart as cart_routes
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.route_served_place import RouteServedPlace
from app.features.shipping.services.last_leg import (
    resolve_last_leg_candidates,
    resolve_last_leg_options,
)

WAREHOUSE = uuid.uuid4()
SHOP_PAPEETE = uuid.uuid4()
SHOP_TARAVAO = uuid.uuid4()
TAHITI = uuid.uuid4()
MOOREA = uuid.uuid4()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _route(
    name: str,
    *,
    delivery_type: str,
    mode: str,
    to: uuid.UUID,
    priority: int = 0,
    always: bool = True,
) -> ShippingRoute:
    return ShippingRoute(
        id=uuid.uuid4(),
        name=name,
        from_place_id=WAREHOUSE,
        to_place_id=to,
        mode=mode,
        is_to_customer=True,
        last_leg_delivery_type=delivery_type,
        always_available=always,
        priority=priority,
    )


def _session(routes: list[ShippingRoute], served: list[RouteServedPlace]) -> Any:
    session = MagicMock()
    results = []
    for rows in (routes, served):
        result = MagicMock()
        result.all.return_value = rows
        results.append(result)
    session.exec = AsyncMock(side_effect=results)
    return session


def _pickup(name: str, to: uuid.UUID, **kw: Any) -> ShippingRoute:
    return _route(name, delivery_type="pickup", mode="pickup", to=to, **kw)


@pytest.mark.anyio
async def test_each_pickup_point_is_an_offer() -> None:
    papeete = _pickup("Retrait Papeete", SHOP_PAPEETE)
    taravao = _pickup("Retrait Taravao", SHOP_TARAVAO, priority=1)
    home = _route("Domicile", delivery_type="home_delivery", mode="road", to=TAHITI)
    session = _session([papeete, taravao, home], [])

    offers = await resolve_last_leg_options(session, [TAHITI])

    assert [o.route.name for o in offers] == [
        "Domicile",
        "Retrait Papeete",
        "Retrait Taravao",
    ]
    assert offers[1].pickup_place_id == SHOP_PAPEETE
    assert offers[0].pickup_place_id is None


@pytest.mark.anyio
async def test_best_per_mode_is_still_one_pickup() -> None:
    papeete = _pickup("Retrait Papeete", SHOP_PAPEETE, priority=2)
    taravao = _pickup("Retrait Taravao", SHOP_TARAVAO, priority=1)
    session = _session([taravao, papeete], [])

    best = await resolve_last_leg_candidates(session, [TAHITI])

    assert list(best) == ["pickup"]
    assert best["pickup"].route is taravao


@pytest.mark.anyio
async def test_same_pickup_point_keeps_the_most_specific_route() -> None:
    everywhere = _pickup("Retrait partout", SHOP_PAPEETE)
    tahiti_only = _pickup("Retrait Tahiti", SHOP_PAPEETE, always=False)
    served = [RouteServedPlace(route_id=tahiti_only.id, place_id=TAHITI)]
    session = _session([everywhere, tahiti_only], served)

    offers = await resolve_last_leg_options(session, [TAHITI])

    assert [o.route.name for o in offers] == ["Retrait Tahiti"]


@pytest.mark.anyio
async def test_pickup_point_scoped_elsewhere_is_not_offered() -> None:
    papeete = _pickup("Retrait Papeete", SHOP_PAPEETE)
    moorea_only = _pickup("Retrait Moorea", SHOP_TARAVAO, always=False)
    served = [RouteServedPlace(route_id=moorea_only.id, place_id=MOOREA)]
    session = _session([papeete, moorea_only], served)

    offers = await resolve_last_leg_options(session, [TAHITI])

    assert [o.route.name for o in offers] == ["Retrait Papeete"]


@pytest.mark.anyio
async def test_home_deliveries_still_collapse_to_one_offer() -> None:
    a = _route("Domicile A", delivery_type="home_delivery", mode="road", to=TAHITI)
    b = _route("Domicile B", delivery_type="home_delivery", mode="road", to=MOOREA)
    session = _session([a, b], [])

    offers = await resolve_last_leg_options(session, [TAHITI])

    assert [o.route.name for o in offers] == ["Domicile A"]


@pytest.mark.anyio
async def test_checkout_resolves_the_chosen_pickup_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    papeete = _pickup("Retrait Papeete", SHOP_PAPEETE)
    taravao = _pickup("Retrait Taravao", SHOP_TARAVAO, priority=1)

    async def _options(_session_arg: Any, destination_chain: list[uuid.UUID]) -> Any:
        return await resolve_last_leg_options(
            _session([papeete, taravao], []), destination_chain
        )

    monkeypatch.setattr(cart_routes, "resolve_last_leg_options", _options)
    resolve = cart_routes._resolve_last_leg_route

    chosen = await resolve(
        MagicMock(), delivery_type="pickup", pickup_place_id=SHOP_TARAVAO
    )
    default = await resolve(MagicMock(), delivery_type="pickup")
    unknown = await resolve(MagicMock(), delivery_type="pickup", pickup_place_id=MOOREA)

    assert chosen is taravao
    assert default is papeete  # best offer when no point is chosen
    assert unknown is None  # → checkout.delivery_type.unavailable
