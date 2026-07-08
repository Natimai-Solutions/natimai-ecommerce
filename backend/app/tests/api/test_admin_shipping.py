"""Unit tests for the admin logistics endpoints (Phase 4)."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.admin_shipping import (
    ShipRequest,
    advance_tracking,
    deliver_tracking,
    list_pending_grouping,
    ship_tracking,
)
from app.core.errors import AppError
from app.features.shipping.crud import (
    crud_shipping_route_tracking,
    crud_status_definition,
)
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _status(code: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), code=code, name=name)


@pytest.mark.anyio
async def test_ship_tracking_sets_status_ref_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = cast(User, SimpleNamespace(id=uuid4()))
    session = AsyncMock()
    session.add = Mock()

    shipped = _status("shipped", "Expédiée")
    tracking = SimpleNamespace(
        id=uuid4(),
        order_id=uuid4(),
        status_id=shipped.id,
        tracking_ref=None,
        estimated_delivery=None,
    )

    monkeypatch.setattr(
        crud_status_definition, "get_by_code", AsyncMock(return_value=shipped)
    )
    update_status = AsyncMock(return_value=tracking)
    monkeypatch.setattr(crud_shipping_route_tracking, "update_status", update_status)
    publish = AsyncMock()
    monkeypatch.setattr(outbox_registry, "publish", publish)

    response = await ship_tracking(
        tracking_id=tracking.id,
        body=ShipRequest(tracking_ref="CARRIER-123"),
        session=session,
        admin=admin,
    )

    assert "expédié" in response.message.lower()

    # Forced transition to the resolved "shipped" status id.
    assert update_status.await_args is not None
    assert update_status.await_args.kwargs["new_status_id"] == shipped.id
    assert update_status.await_args.kwargs["force"] is True
    # Carrier ref stamped on the tracking.
    assert tracking.tracking_ref == "CARRIER-123"
    # Customer notification event published with the ref.
    assert publish.await_args is not None
    assert publish.await_args.kwargs["event_type"] == "tracking.status_changed"
    assert publish.await_args.kwargs["payload"]["tracking_ref"] == "CARRIER-123"
    assert publish.await_args.kwargs["payload"]["status_code"] == "shipped"
    session.commit.assert_awaited()


@pytest.mark.anyio
async def test_deliver_tracking_marks_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = cast(User, SimpleNamespace(id=uuid4()))
    session = AsyncMock()
    session.add = Mock()

    delivered = _status("delivered", "Livrée")
    tracking = SimpleNamespace(
        id=uuid4(),
        order_id=uuid4(),
        status_id=delivered.id,
        tracking_ref="CARRIER-123",
        estimated_delivery=None,
    )

    monkeypatch.setattr(
        crud_status_definition, "get_by_code", AsyncMock(return_value=delivered)
    )
    monkeypatch.setattr(
        crud_shipping_route_tracking,
        "update_status",
        AsyncMock(return_value=tracking),
    )
    publish = AsyncMock()
    monkeypatch.setattr(outbox_registry, "publish", publish)

    response = await deliver_tracking(
        tracking_id=tracking.id, session=session, admin=admin
    )

    assert "livré" in response.message.lower()
    assert publish.await_args is not None
    assert publish.await_args.kwargs["payload"]["status_code"] == "delivered"
    session.commit.assert_awaited()


@pytest.mark.anyio
async def test_pending_grouping_enriches_status_and_flags_final_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = cast(User, SimpleNamespace(id=uuid4()))
    session = AsyncMock()

    pending = _status("pending", "En attente")
    order_id = uuid4()
    first_leg = SimpleNamespace(
        id=uuid4(),
        order_id=order_id,
        route_id=uuid4(),
        sequence_order=1,
        status_id=pending.id,
        tracking_ref=None,
    )
    last_leg = SimpleNamespace(
        id=uuid4(),
        order_id=order_id,
        route_id=uuid4(),
        sequence_order=2,
        status_id=pending.id,
        tracking_ref=None,
    )

    monkeypatch.setattr(
        crud_shipping_route_tracking,
        "get_unconsolidated_trackings",
        AsyncMock(return_value=[first_leg, last_leg]),
    )
    monkeypatch.setattr(
        crud_status_definition,
        "get_by_entity",
        AsyncMock(return_value=[pending]),
    )
    # Two exec calls: last-leg route ids (is_to_customer), then max sequence per
    # order. The second leg's route is a customer-delivery route.
    routes_result = Mock()
    routes_result.all = Mock(return_value=[last_leg.route_id])
    sequences_result = Mock()
    sequences_result.all = Mock(return_value=[(order_id, 2)])
    session.exec = AsyncMock(side_effect=[routes_result, sequences_result])

    items = await list_pending_grouping(session=session, _admin=admin)

    assert len(items) == 2
    assert items[0].tracking_id == first_leg.id
    assert items[0].status_code == "pending"
    assert items[0].status_name == "En attente"
    # Leg 1/2 is intermediate → « Tronçon suivant » ; leg 2/2 is the customer
    # delivery → « Livrer ».
    assert items[0].is_final_leg is False
    assert items[1].is_final_leg is True


@pytest.mark.anyio
async def test_advance_tracking_refuses_customer_delivery_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advancing the last leg would strand it `completed` — must 400 instead."""
    admin = cast(User, SimpleNamespace(id=uuid4()))
    session = AsyncMock()

    tracking = SimpleNamespace(id=uuid4(), route_id=uuid4())
    route = SimpleNamespace(id=tracking.route_id, is_to_customer=True)
    session.get = AsyncMock(side_effect=[tracking, route])

    activate = AsyncMock()
    monkeypatch.setattr(
        crud_shipping_route_tracking, "activate_next_route", activate
    )

    with pytest.raises(AppError) as exc:
        await advance_tracking(
            tracking_id=tracking.id, session=session, admin=admin
        )

    assert exc.value.status_code == 400
    assert exc.value.code == "shipping.advance.last_leg"
    activate.assert_not_awaited()
