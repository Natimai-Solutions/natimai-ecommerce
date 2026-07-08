"""Integration tests: the first leg is resolved from the supplier origin place."""

from types import SimpleNamespace

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import (
    FulfillmentSegment,
    _get_main_warehouse_place_id,
    _resolve_tracking_route_for_segment,
)
from app.features.place.models import Place
from app.features.shipping.models.route import ShippingRoute


async def _seed_corridor(session: AsyncSession) -> SimpleNamespace:
    """Supplier (FR) → main warehouse (Papeete) via the default import route."""
    fr = Place(name="Fournisseur FR", type="warehouse")
    ppt = Place(name="Entrepôt Papeete", type="warehouse", is_warehouse=True)
    session.add_all([fr, ppt])
    await session.flush()

    route = ShippingRoute(
        from_place_id=fr.id,
        to_place_id=ppt.id,
        name="FR→PF",
        mode="sea",
        is_default_import=True,
    )
    session.add(route)
    await session.flush()
    return SimpleNamespace(fr=fr, ppt=ppt, route=route)


@pytest.mark.asyncio
async def test_main_warehouse_is_import_destination(db_session: AsyncSession) -> None:
    seed = await _seed_corridor(db_session)
    warehouse_id = await _get_main_warehouse_place_id(db_session)
    assert warehouse_id == seed.ppt.id


@pytest.mark.asyncio
async def test_route_resolved_from_supplier_origin(db_session: AsyncSession) -> None:
    seed = await _seed_corridor(db_session)
    route = await _resolve_tracking_route_for_segment(
        session=db_session,
        segment=FulfillmentSegment.SUPPLIER_DIRECT,
        origin_place_id=seed.fr.id,
    )
    # First leg = the route leaving the supplier's origin place.
    assert route is not None
    assert route.id == seed.route.id


@pytest.mark.asyncio
async def test_falls_back_to_heuristic_without_origin(
    db_session: AsyncSession,
) -> None:
    # No origin place → the generic heuristic still returns an active route.
    seed = await _seed_corridor(db_session)
    route = await _resolve_tracking_route_for_segment(
        session=db_session,
        segment=FulfillmentSegment.SUPPLIER_DIRECT,
        origin_place_id=None,
    )
    assert route is not None
    assert route.id == seed.route.id
