"""Integration tests: the admin start-up checklist is computed from the data."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_setup_checklist as checklist
from app.features.payment.models.payment_method import PaymentMethod
from app.features.place.models import Place
from app.features.product.models.product import PricingMode, Product
from app.features.system.legal_identity import REQUIRED_FOR_INVOICING
from app.features.user.models.user import User


def _settings(monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]) -> None:
    async def _get(key: str, _session: object = None, **_kw: object) -> Any:
        return values.get(key)

    monkeypatch.setattr("app.core.runtime_settings.get", _get)


def _legal(monkeypatch: pytest.MonkeyPatch, identity: dict[str, str]) -> None:
    async def _load(_session: object) -> dict[str, str]:
        return identity

    monkeypatch.setattr(checklist, "load_legal_identity", _load)


def _statuses(result: checklist.SetupChecklist) -> dict[str, tuple[str, int]]:
    return {item.key: (item.status, item.count) for item in result.items}


@pytest.mark.asyncio
async def test_a_new_shop_has_everything_to_do(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, {})
    _legal(monkeypatch, {})

    result = await checklist.get_setup_checklist(db_session, cast(User, None))

    statuses = _statuses(result)
    assert statuses["legal_identity"] == ("todo", len(REQUIRED_FOR_INVOICING))
    assert statuses["support_email"][0] == "todo"
    assert statuses["payment_methods"][0] == "todo"
    assert statuses["catalogue"] == ("todo", 0)
    assert statuses["insurance_rate"][0] == "check"
    assert not result.ready
    assert result.total == len(result.items)


@pytest.mark.asyncio
async def test_a_configured_shop_only_misses_its_catalogue(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, {"email_support": "boutique@example.pf"})
    _legal(monkeypatch, dict.fromkeys(REQUIRED_FOR_INVOICING, "x"))
    db_session.add(PaymentMethod(name="Virement", provider_code="manual"))
    db_session.add(
        Place(
            name="Port de Papeete", type="port", code="PPT-PORT", customs_clearance=True
        )
    )
    db_session.add(
        Place(
            name="Aéroport de Faa'a",
            type="airport",
            code="PPT-AIR",
            customs_clearance=True,
            customs_declaration_fee=Decimal("3500"),
        )
    )
    await db_session.commit()

    result = await checklist.get_setup_checklist(db_session, cast(User, None))

    statuses = _statuses(result)
    assert statuses["legal_identity"] == ("done", 0)
    assert statuses["support_email"][0] == "done"
    assert statuses["payment_methods"][0] == "done"
    # One clearance place has no declaration fee: to confirm, not blocking.
    assert statuses["customs_declaration_fees"] == ("check", 1)
    assert statuses["insurance_rate"][0] == "check"
    # The empty catalogue is the only thing left.
    assert [k for k, (s, _) in statuses.items() if s == "todo"] == ["catalogue"]
    assert not result.ready


@pytest.mark.asyncio
async def test_the_catalogue_is_counted_as_the_storefront_publishes_it(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A classic shop: products entered by hand (never enriched by Icecat),
    sold at a fixed price. They are online, and neither a customs rate nor a
    weight is needed for them: the checklist must not ask for one."""
    _settings(monkeypatch, {})
    _legal(monkeypatch, {})
    db_session.add_all(
        [
            Product(
                name="Câble HDMI",
                description="",
                base_price=Decimal("2500"),
                pricing_mode=PricingMode.FIXED,
                is_supplier_managed=False,
            ),
            # A supplier line still waiting for Icecat: not online yet.
            Product(
                name="SKU-IM-1",
                description="",
                base_price=Decimal("1"),
                is_supplier_managed=True,
            ),
        ]
    )
    await db_session.commit()

    statuses = _statuses(
        await checklist.get_setup_checklist(db_session, cast(User, None))
    )

    assert statuses["catalogue"] == ("done", 1)
    assert statuses["customs_rates"] == ("done", 0)
    assert statuses["weights"] == ("done", 0)


@pytest.mark.asyncio
async def test_import_routes_and_their_fixed_cost_are_checked(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of 17/11/2026 and decision of 18/11/2026: imported articles
    with no import route carrying a service level were sold without freight;
    a fixed cost with no weight to spread it over is billed nowhere."""
    from app.features.shipping.models.route import ShippingRoute

    _settings(monkeypatch, {})
    _legal(monkeypatch, {})
    db_session.add(
        Product(
            name="Écran",
            description="",
            base_price=Decimal("10000"),
            pricing_mode=PricingMode.IMPORT,
            is_supplier_managed=False,
        )
    )
    await db_session.commit()

    async def statuses() -> dict[str, tuple[str, int]]:
        return _statuses(
            await checklist.get_setup_checklist(db_session, cast(User, None))
        )

    assert (await statuses())["import_routes"][0] == "todo"

    hub = Place(name="Hub", type="warehouse", is_warehouse=True, country="FR")
    papeete = Place(name="Papeete", type="warehouse", is_warehouse=True, country="PF")
    db_session.add_all([hub, papeete])
    await db_session.flush()
    route = ShippingRoute(
        from_place_id=hub.id,
        to_place_id=papeete.id,
        name="Import avion",
        mode="air",
        service_level="rapide",
        price_per_kg=Decimal("700"),
        base_price=Decimal("15000"),
    )
    db_session.add(route)
    await db_session.flush()
    route_id = route.id
    await db_session.commit()
    now = await statuses()
    assert now["import_routes"][0] == "done"
    assert now["import_fixed_cost"] == ("todo", 1)

    saved = await db_session.get(ShippingRoute, route_id)
    assert saved is not None
    saved.import_fixed_basis_kg = Decimal("200")
    db_session.add(saved)
    await db_session.commit()
    assert (await statuses())["import_fixed_cost"] == ("done", 0)
