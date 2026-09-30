"""Modules switched off hide their routes, crons and checkout options (R4 / S7)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.routing import APIRoute
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import module_required
from app.api.routes import (
    admin_carts,
    admin_currency_rates,
    admin_grouped_departures,
    admin_quote_requests,
    admin_spec_definitions,
    admin_supplier_orders,
    admin_suppliers,
    cart,
    group_upgrade,
    suppliers,
)
from app.api.routes.grouped_departures import next_departure
from app.core.config import settings
from app.core.errors import AppError
from app.features import initial_data as seed
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.system.models.system_setting import SystemSetting
from app.features.system.modules import MODULES, module_enabled, set_module
from app.features.user.models.user import User
from app.tasks.supplier_tasks import _due_suppliers


def _gated_by(router: object) -> set[str]:
    names = {d.dependency.__name__ for d in getattr(router, "dependencies", [])}
    return {n.removeprefix("module_required_") for n in names}


def _route_gates(router: object, path_part: str) -> set[str]:
    gates: set[str] = set()
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute) and path_part in route.path:
            gates |= {
                d.call.__name__.removeprefix("module_required_")
                for d in route.dependant.dependencies
                if d.call is not None and d.call.__name__.startswith("module_required_")
            }
    return gates


def test_admin_routers_carry_their_module() -> None:
    assert _gated_by(admin_suppliers.router) == {"suppliers"}
    assert _gated_by(suppliers.router) == {"suppliers"}
    assert _gated_by(admin_supplier_orders.router) == {"supplier_orders"}
    assert _gated_by(admin_currency_rates.router) == {"currencies"}
    assert _gated_by(admin_spec_definitions.router) == {"specs"}
    assert _gated_by(admin_grouped_departures.router) == {"grouped_departures"}
    assert _gated_by(admin_quote_requests.router) == {"quotes"}
    assert _gated_by(admin_carts.router) == {"abandoned_carts"}
    assert _gated_by(group_upgrade.router) == {"price_groups"}
    assert "file_import" in _route_gates(suppliers.router, "import-file")
    assert "quotes" in _route_gates(cart.router, "quote-request")


@pytest.mark.asyncio
async def test_a_switched_off_module_answers_an_explicit_404(
    db_session: AsyncSession,
) -> None:
    gate = module_required("quotes")
    await gate(db_session)  # on by default (full shop)

    await set_module(db_session, "quotes", False)
    await db_session.commit()
    with pytest.raises(AppError) as refused:
        await gate(db_session)
    assert refused.value.status_code == 404
    assert refused.value.code == "module.disabled"


@pytest.mark.asyncio
async def test_departures_banner_and_deposits_follow_their_switch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_departure: Any = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(
        "app.api.routes.grouped_departures.crud_grouped_departure.get_next_open",
        lambda _session: _async(open_departure),
    )
    monkeypatch.setattr(
        "app.api.routes.grouped_departures.GroupedDepartureSummary.model_validate",
        lambda obj: obj,
    )
    assert await next_departure(db_session) is open_departure
    await set_module(db_session, "grouped_departures", False)
    await db_session.commit()
    assert await next_departure(db_session) is None

    group = SimpleNamespace(deposit_pct=Decimal("30"), deposit_required=True)
    assert (await cart._deposit_policy(db_session, group)).available is True
    await set_module(db_session, "deposits", False)
    await db_session.commit()
    assert (await cart._deposit_policy(db_session, group)).available is False


async def _async(value: object) -> object:
    return value


@pytest.mark.asyncio
async def test_supplier_ticks_idle_while_suppliers_are_off(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = []

    async def fake_api_suppliers(_session: AsyncSession) -> list[object]:
        called.append(True)
        return []

    monkeypatch.setattr("app.tasks.supplier_tasks.api_suppliers", fake_api_suppliers)
    await set_module(db_session, "suppliers", False)
    await db_session.commit()
    assert await _due_suppliers(db_session, catalog=True) == []
    assert called == []


async def _switch_values(session: AsyncSession) -> dict[str, str]:
    rows = (
        await session.exec(
            select(SystemSetting).where(SystemSetting.key.startswith("module."))
        )
    ).all()
    return {row.key.removeprefix("module."): row.value for row in rows}


@pytest.mark.asyncio
async def test_simple_preset_for_a_new_shop(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SHOP_MODE", "simple")
    await seed._seed_module_switches(db_session)
    await db_session.commit()
    values = await _switch_values(db_session)
    assert set(values) == {spec.key for spec in MODULES}
    on = {key for key, value in values.items() if value == "true"}
    assert on == {"suppliers", "file_import"}


@pytest.mark.asyncio
async def test_an_existing_simple_shop_keeps_what_it_showed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    buyer = User(email="c@test.local", hashed_password="x")
    status = OrderStatus(name="Paid")
    db_session.add_all([buyer, status])
    await db_session.flush()
    db_session.add(
        Order(
            user_id=buyer.id,
            order_status_id=status.id,
            order_number="CMD-1",
            total_amount=Decimal("10"),
        )
    )
    await db_session.commit()

    monkeypatch.setattr(settings, "SHOP_MODE", "simple")
    await seed._seed_module_switches(db_session)
    await db_session.commit()
    values = await _switch_values(db_session)
    assert values["quotes"] == "true"
    assert values["deposits"] == "true"
    assert values["grouped_departures"] == "true"
    assert values["customs"] == "false"
    assert values["icecat"] == "false"
    assert await module_enabled(db_session, "quotes") is True
