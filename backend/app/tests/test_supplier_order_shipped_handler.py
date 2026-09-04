"""Unit tests for the supplier_order.shipped outbox handler (audit item Q3).

Ce handler est le seul chemin par lequel un webhook fournisseur fait avancer le
suivi d'expédition côté client. Il est écrit pour ne jamais faire échouer
l'événement — payload incomplet, statut absent, transition refusée : il
journalise et sort. C'est le bon comportement (l'admin corrige à la main), mais
cela veut dire qu'**aucune erreur ne remonte** : seuls des tests disent encore
qu'il avance ce qu'il doit avancer, et rien d'autre.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_status_definition,
)
from app.handlers.supplier_order import on_supplier_order_shipped


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _tracking(status_id: uuid.UUID | None = None) -> Any:
    return SimpleNamespace(id=uuid.uuid4(), status_id=status_id or uuid.uuid4())


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    shipped_status: Any | None,
    trackings: list[Any],
    update_side_effect: Any = None,
) -> tuple[AsyncMock, AsyncMock]:
    """Patch les trois appels CRUD du handler et rend les espions utiles."""
    get_status = AsyncMock(return_value=shipped_status)
    get_trackings = AsyncMock(return_value=trackings)
    update_status = AsyncMock(side_effect=update_side_effect)

    monkeypatch.setattr(crud_status_definition, "get_by_code", get_status)
    monkeypatch.setattr(
        crud_shipping_route_tracking,
        "get_trackings_by_order_sequence",
        get_trackings,
    )
    monkeypatch.setattr(crud_shipping_route_tracking, "update_status", update_status)
    return get_status, update_status


# ---------------------------------------------------------------------------
# Payload inexploitable
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_missing_order_id_stops_before_any_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_status, update_status = _wire(
        monkeypatch, shipped_status=SimpleNamespace(id=uuid.uuid4()), trackings=[]
    )

    await on_supplier_order_shipped(MagicMock(), {})

    get_status.assert_not_awaited()
    update_status.assert_not_awaited()


@pytest.mark.anyio
async def test_unparseable_order_id_stops_before_any_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_status, update_status = _wire(
        monkeypatch, shipped_status=SimpleNamespace(id=uuid.uuid4()), trackings=[]
    )

    await on_supplier_order_shipped(MagicMock(), {"local_order_id": "pas-un-uuid"})

    get_status.assert_not_awaited()
    update_status.assert_not_awaited()


# ---------------------------------------------------------------------------
# Rien à faire
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_missing_shipped_status_definition_is_survived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Base mal amorcée : on sort sans toucher aux suivis."""
    _get_status, update_status = _wire(
        monkeypatch, shipped_status=None, trackings=[_tracking()]
    )

    await on_supplier_order_shipped(MagicMock(), {"local_order_id": str(uuid.uuid4())})

    update_status.assert_not_awaited()


@pytest.mark.anyio
async def test_order_without_tracking_advances_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _get_status, update_status = _wire(
        monkeypatch, shipped_status=SimpleNamespace(id=uuid.uuid4()), trackings=[]
    )

    await on_supplier_order_shipped(MagicMock(), {"local_order_id": str(uuid.uuid4())})

    update_status.assert_not_awaited()


# ---------------------------------------------------------------------------
# Avancement
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pending_trackings_are_advanced_to_shipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipped = SimpleNamespace(id=uuid.uuid4())
    pending = _tracking()
    _get_status, update_status = _wire(
        monkeypatch, shipped_status=shipped, trackings=[pending]
    )
    session = MagicMock()
    order_id = uuid.uuid4()

    await on_supplier_order_shipped(
        session,
        {"local_order_id": str(order_id), "supplier_status_label": "SHIPPED"},
    )

    update_status.assert_awaited_once()
    assert update_status.await_args is not None
    kwargs = update_status.await_args.kwargs
    assert kwargs["tracking_id"] == pending.id
    assert kwargs["new_status_id"] == shipped.id
    assert kwargs["changed_by"] == "supplier_webhook"
    # Le libellé fournisseur est repris tel quel : c'est la trace de la décision.
    assert "SHIPPED" in kwargs["reason"]


@pytest.mark.anyio
async def test_already_shipped_trackings_are_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Idempotence : un webhook rejoué ne réécrit pas un suivi déjà expédié."""
    shipped = SimpleNamespace(id=uuid.uuid4())
    _get_status, update_status = _wire(
        monkeypatch,
        shipped_status=shipped,
        trackings=[_tracking(status_id=shipped.id)],
    )

    await on_supplier_order_shipped(MagicMock(), {"local_order_id": str(uuid.uuid4())})

    update_status.assert_not_awaited()


@pytest.mark.anyio
async def test_a_refused_transition_does_not_stop_the_other_trackings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une transition interdite sur un segment ne doit pas bloquer les autres."""
    shipped = SimpleNamespace(id=uuid.uuid4())
    first, second = _tracking(), _tracking()
    calls: list[uuid.UUID] = []

    async def _update(**kwargs: Any) -> None:
        calls.append(kwargs["tracking_id"])
        if kwargs["tracking_id"] == first.id:
            raise ValueError("transition not allowed")

    monkeypatch.setattr(
        crud_status_definition, "get_by_code", AsyncMock(return_value=shipped)
    )
    monkeypatch.setattr(
        crud_shipping_route_tracking,
        "get_trackings_by_order_sequence",
        AsyncMock(return_value=[first, second]),
    )
    monkeypatch.setattr(
        crud_shipping_route_tracking, "update_status", AsyncMock(side_effect=_update)
    )

    await on_supplier_order_shipped(MagicMock(), {"local_order_id": str(uuid.uuid4())})

    assert calls == [first.id, second.id]


@pytest.mark.anyio
async def test_the_shipped_status_is_looked_up_for_route_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le code de statut est partagé entre entités : l'entité doit être précisée."""
    get_status, _update = _wire(
        monkeypatch, shipped_status=SimpleNamespace(id=uuid.uuid4()), trackings=[]
    )

    await on_supplier_order_shipped(MagicMock(), {"local_order_id": str(uuid.uuid4())})

    assert get_status.await_args is not None
    assert get_status.await_args.kwargs == {
        "entity": "route_tracking",
        "code": "shipped",
    }
