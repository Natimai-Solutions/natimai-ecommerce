"""Unit tests for the import-leg double-charge guard (audit item F6).

An import route (destination clears customs) already has its variable freight
baked into the product's CAF unit price. Billing it again as a cart shipping fee
charges the customer twice for the same leg — once invisibly in the price, once
in the shipping line.

The DB is mocked: only the selection logic is under test, not the tariff.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.api.routes.cart import (
    _import_route_ids,
    _resolve_selected_checkout_routes,
    _select_checkout_routes_by_preference,
)
from app.core.errors import AppError
from app.features.cart.models.cart import CheckoutShippingPreference
from app.features.shipping.crud import crud_shipping_route


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _route(*, to_place_id: UUID, name: str = "route", priority: int = 1) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        to_place_id=to_place_id,
        name=name,
        priority=priority,
        eta_days=5,
        carbon_footprint_kg_co2e=1.0,
        is_active=True,
        price_per_kg=Decimal("100"),
        base_price=Decimal("0"),
        mode="air",
        route_metadata=None,
    )


def _session(
    *,
    customs_place_ids: set[UUID],
    routes: list[Any] | None = None,
) -> Any:
    """Session answering both the route lookup and the customs-place lookup.

    The two queries are told apart by call order: the route fetch comes first in
    ``_resolve_selected_checkout_routes``, the customs-place fetch second.
    """
    calls: list[Any] = []

    async def _exec(_stmt: Any) -> Any:
        result = MagicMock()
        calls.append(_stmt)
        if routes is not None and len(calls) == 1:
            result.all.return_value = routes
        else:
            result.all.return_value = list(customs_place_ids)
        return result

    session = MagicMock()
    session.exec = AsyncMock(side_effect=_exec)
    return session


# ---------------------------------------------------------------------------
# _import_route_ids
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_flags_routes_landing_on_a_customs_place() -> None:
    papeete = uuid4()
    moorea = uuid4()
    import_leg = _route(to_place_id=papeete, name="France → Papeete")
    local_leg = _route(to_place_id=moorea, name="Papeete → Moorea")

    flagged = await _import_route_ids(
        _session(customs_place_ids={papeete}), [import_leg, local_leg]
    )

    assert flagged == {import_leg.id}


@pytest.mark.anyio
async def test_no_routes_means_no_query() -> None:
    session = _session(customs_place_ids=set())

    assert await _import_route_ids(session, []) == set()
    session.exec.assert_not_awaited()


# ---------------------------------------------------------------------------
# Client-supplied routes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_client_cannot_bill_an_import_route() -> None:
    papeete = uuid4()
    import_leg = _route(to_place_id=papeete, name="France → Papeete")
    session = _session(customs_place_ids={papeete}, routes=[import_leg])

    with pytest.raises(AppError) as exc_info:
        await _resolve_selected_checkout_routes(
            session, shipping_route_ids=[import_leg.id]
        )

    assert exc_info.value.code == "shipping.route.import_not_billable"
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_domestic_routes_are_still_billable() -> None:
    moorea = uuid4()
    local_leg = _route(to_place_id=moorea, name="Papeete → Moorea")
    session = _session(customs_place_ids=set(), routes=[local_leg])

    resolved = await _resolve_selected_checkout_routes(
        session, shipping_route_ids=[local_leg.id]
    )

    assert [r.id for r in resolved] == [local_leg.id]


# ---------------------------------------------------------------------------
# Automatic selection — the path the storefront actually uses
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_auto_selection_skips_the_import_leg(monkeypatch: Any) -> None:
    """get_intermediary_routes returns every non-customer route, imports included."""
    papeete = uuid4()
    tahiti_hub = uuid4()
    import_leg = _route(to_place_id=papeete, name="France → Papeete", priority=1)
    consolidation_leg = _route(to_place_id=tahiti_hub, name="Hub PF", priority=2)
    customer_leg = _route(to_place_id=uuid4(), name="Livraison", priority=3)

    async def _intermediary(**_kwargs: Any) -> list[Any]:
        return [import_leg, consolidation_leg]

    async def _customer(**_kwargs: Any) -> list[Any]:
        return [customer_leg]

    # cart.py holds a reference to this very singleton, so patching it here
    # reaches the code under test.
    monkeypatch.setattr(crud_shipping_route, "get_intermediary_routes", _intermediary)
    monkeypatch.setattr(crud_shipping_route, "get_customer_routes", _customer)

    selected = await _select_checkout_routes_by_preference(
        _session(customs_place_ids={papeete}),
        preference=CheckoutShippingPreference.CHEAPEST,
        total_weight_kg=Decimal("2"),
        declared_value=Decimal("100000"),
        currency="XPF",
    )

    selected_ids = {r.id for r in selected}
    assert import_leg.id not in selected_ids
    assert consolidation_leg.id in selected_ids
