"""Unit tests for the admin logistics endpoints (Phase 4)."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes import admin_shipping
from app.api.routes.admin_shipping import (
    ShipRequest,
    deliver_tracking,
    list_pending_grouping,
    ship_tracking,
)
from app.features.user.models.user import User


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
        admin_shipping.crud_status_definition,
        "get_by_code",
        AsyncMock(return_value=shipped),
    )
    update_status = AsyncMock(return_value=tracking)
    monkeypatch.setattr(
        admin_shipping.crud_shipping_route_tracking, "update_status", update_status
    )
    publish = AsyncMock()
    monkeypatch.setattr(admin_shipping.outbox_registry, "publish", publish)

    response = await ship_tracking(
        tracking_id=tracking.id,
        body=ShipRequest(tracking_ref="CARRIER-123"),
        session=session,
        admin=admin,
    )

    assert "expédié" in response.message.lower()
    # Forced transition to the resolved "shipped" status id.
    assert update_status.await_args.kwargs["new_status_id"] == shipped.id
    assert update_status.await_args.kwargs["force"] is True
    # Carrier ref stamped on the tracking.
    assert tracking.tracking_ref == "CARRIER-123"
    # Customer notification event published with the ref.
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
        admin_shipping.crud_status_definition,
        "get_by_code",
        AsyncMock(return_value=delivered),
    )
    monkeypatch.setattr(
        admin_shipping.crud_shipping_route_tracking,
        "update_status",
        AsyncMock(return_value=tracking),
    )
    publish = AsyncMock()
    monkeypatch.setattr(admin_shipping.outbox_registry, "publish", publish)

    response = await deliver_tracking(
        tracking_id=tracking.id, session=session, admin=admin
    )

    assert "livré" in response.message.lower()
    assert publish.await_args.kwargs["payload"]["status_code"] == "delivered"
    session.commit.assert_awaited()


@pytest.mark.anyio
async def test_pending_grouping_enriches_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = cast(User, SimpleNamespace(id=uuid4()))
    session = AsyncMock()

    pending = _status("pending", "En attente")
    tracking = SimpleNamespace(
        id=uuid4(),
        order_id=uuid4(),
        route_id=uuid4(),
        sequence_order=1,
        status_id=pending.id,
        tracking_ref=None,
    )

    monkeypatch.setattr(
        admin_shipping.crud_shipping_route_tracking,
        "get_unconsolidated_trackings",
        AsyncMock(return_value=[tracking]),
    )
    monkeypatch.setattr(
        admin_shipping.crud_status_definition,
        "get_by_entity",
        AsyncMock(return_value=[pending]),
    )

    items = await list_pending_grouping(session=session, _admin=admin)

    assert len(items) == 1
    assert items[0].tracking_id == tracking.id
    assert items[0].status_code == "pending"
    assert items[0].status_name == "En attente"
