"""Integration (real DB): a route into a customs clearance place needs a mode.

Review of 17/11/2026, decision of 18/11/2026: the article price holds the
freight of the routes carrying a mode, the checkout leaves out every route
ending where customs clear. A route into customs without a mode fell between
the two — its freight was billed nowhere. Saving one is refused; those saved
before are listed by the setup checklist."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_setup_checklist as checklist
from app.core.errors import AppError
from app.features.place.models import Place
from app.features.shipping.crud.route import crud_shipping_route as crud_route
from app.features.shipping.models.route import (
    ShippingRoute,
    ShippingRouteCreate,
    ShippingRouteUpdate,
)
from app.features.user.models.user import User


async def _places(session: AsyncSession) -> tuple[Any, Any, Any]:
    hub = Place(name="Hub", type="warehouse", is_warehouse=True, country="FR")
    papeete = Place(
        name="Papeete", type="warehouse", is_warehouse=True, customs_clearance=True
    )
    shop = Place(name="Boutique", type="warehouse", is_warehouse=True)
    session.add_all([hub, papeete, shop])
    await session.flush()
    ids = (hub.id, papeete.id, shop.id)
    await session.commit()
    return ids


def _route(from_id: Any, to_id: Any, **extra: Any) -> ShippingRouteCreate:
    return ShippingRouteCreate(
        name="Bateau groupage",
        from_place_id=from_id,
        to_place_id=to_id,
        mode="sea",
        price_per_kg=Decimal("150"),
        **extra,
    )


@pytest.mark.asyncio
async def test_a_route_into_customs_needs_a_mode(db_session: AsyncSession) -> None:
    hub, papeete, shop = await _places(db_session)

    with pytest.raises(AppError) as refused:
        await crud_route.create(db_session, data=_route(hub, papeete), user=None)
    assert refused.value.code == "shipping_route.import_mode_required"
    await db_session.rollback()

    # With its mode it is an import route; elsewhere no mode is needed.
    route = await crud_route.create(
        db_session, data=_route(hub, papeete, service_level="economique"), user=None
    )
    route_id = route.id
    await crud_route.create(db_session, data=_route(papeete, shop), user=None)

    # Its mode cannot be taken away.
    with pytest.raises(AppError) as removed:
        await crud_route.update(
            db_session,
            id=route_id,
            data=ShippingRouteUpdate(service_level=None),
            user=None,
        )
    assert removed.value.code == "shipping_route.import_mode_required"


@pytest.mark.asyncio
async def test_an_old_route_without_mode_is_listed_and_can_be_switched_off(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _get(_key: str, _session: object = None, **_kw: object) -> Any:
        return None

    async def _legal(_session: object) -> dict[str, str]:
        return {}

    monkeypatch.setattr("app.core.runtime_settings.get", _get)
    monkeypatch.setattr(checklist, "load_legal_identity", _legal)
    hub, papeete, _shop = await _places(db_session)
    # Saved before the rule (written straight to the table).
    legacy = ShippingRoute(
        name="Ancienne route",
        from_place_id=hub,
        to_place_id=papeete,
        mode="sea",
        price_per_kg=Decimal("150"),
    )
    db_session.add(legacy)
    await db_session.flush()
    legacy_id = legacy.id
    await db_session.commit()

    async def status() -> tuple[str, int]:
        result = await checklist.get_setup_checklist(db_session, cast(User, None))
        item = next(i for i in result.items if i.key == "import_routes_mode")
        return item.status, item.count

    assert await status() == ("todo", 1)

    await crud_route.update(
        db_session, id=legacy_id, data=ShippingRouteUpdate(is_active=False), user=None
    )
    assert await status() == ("done", 0)
