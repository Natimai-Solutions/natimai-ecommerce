import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.shipping.tracking as tracking_routes
from app.api.deps import get_current_active_superuser
from app.features.shipping.models.route_tracking import ShippingRouteTracking
from app.features.shipping.models.status import StatusDefinition
from app.main import app


@pytest.fixture(autouse=True)
def override_superuser_dependency() -> Generator[None, None, None]:
    async def _override_superuser() -> SimpleNamespace:
        return SimpleNamespace(id=uuid4(), is_superuser=True, is_active=True)

    app.dependency_overrides[get_current_active_superuser] = _override_superuser
    yield
    app.dependency_overrides.clear()


def _build_status(*, code: str, is_terminal: bool, is_error: bool) -> StatusDefinition:
    return StatusDefinition(
        id=uuid4(),
        entity="route_tracking",
        code=code,
        name=code.replace("_", " ").title(),
        description=None,
        sequence_order=0,
        is_terminal=is_terminal,
        is_error=is_error,
        ui_color=None,
        ui_icon=None,
    )


def _build_tracking(
    *,
    order_id: uuid.UUID,
    route_id: uuid.UUID,
    address_id: uuid.UUID,
    status_id: uuid.UUID,
    sequence_order: int,
) -> ShippingRouteTracking:
    return ShippingRouteTracking(
        id=uuid4(),
        order_id=order_id,
        route_id=route_id,
        status_id=status_id,
        address_id=address_id,
        selected_at=datetime.now(timezone.utc),
        sequence_order=sequence_order,
    )


def test_derive_overall_status_prefers_first_non_terminal_sequence() -> None:
    order_id = uuid4()
    route_id = uuid4()
    address_id = uuid4()

    pending_status = _build_status(
        code="pending",
        is_terminal=False,
        is_error=False,
    )
    completed_status = _build_status(
        code="completed",
        is_terminal=True,
        is_error=False,
    )

    trackings = [
        _build_tracking(
            order_id=order_id,
            route_id=route_id,
            address_id=address_id,
            status_id=completed_status.id,
            sequence_order=1,
        ),
        _build_tracking(
            order_id=order_id,
            route_id=route_id,
            address_id=address_id,
            status_id=pending_status.id,
            sequence_order=2,
        ),
    ]

    current_sequence, overall_status = tracking_routes._derive_order_overall_status(
        trackings,
        status_by_id={
            pending_status.id: pending_status,
            completed_status.id: completed_status,
        },
    )

    assert current_sequence == 2
    assert overall_status == "pending"


def test_derive_overall_status_prioritizes_error_segment() -> None:
    order_id = uuid4()
    route_id = uuid4()
    address_id = uuid4()

    in_progress_status = _build_status(
        code="in_progress",
        is_terminal=False,
        is_error=False,
    )
    delayed_status = _build_status(
        code="supplier_delayed",
        is_terminal=False,
        is_error=True,
    )

    trackings = [
        _build_tracking(
            order_id=order_id,
            route_id=route_id,
            address_id=address_id,
            status_id=in_progress_status.id,
            sequence_order=1,
        ),
        _build_tracking(
            order_id=order_id,
            route_id=route_id,
            address_id=address_id,
            status_id=delayed_status.id,
            sequence_order=2,
        ),
    ]

    current_sequence, overall_status = tracking_routes._derive_order_overall_status(
        trackings,
        status_by_id={
            in_progress_status.id: in_progress_status,
            delayed_status.id: delayed_status,
        },
    )

    assert current_sequence == 2
    assert overall_status == "supplier_delayed"


def test_get_order_tracking_exposes_d3_overall_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id = uuid4()
    route_id = uuid4()
    address_id = uuid4()

    completed_status = _build_status(
        code="completed",
        is_terminal=True,
        is_error=False,
    )
    in_progress_status = _build_status(
        code="in_progress",
        is_terminal=False,
        is_error=False,
    )

    first_tracking = _build_tracking(
        order_id=order_id,
        route_id=route_id,
        address_id=address_id,
        status_id=completed_status.id,
        sequence_order=1,
    )
    second_tracking = _build_tracking(
        order_id=order_id,
        route_id=route_id,
        address_id=address_id,
        status_id=in_progress_status.id,
        sequence_order=2,
    )

    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "get_by_order_id",
        AsyncMock(return_value=first_tracking),
    )
    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "get_trackings_by_order_sequence",
        AsyncMock(return_value=[first_tracking, second_tracking]),
    )
    monkeypatch.setattr(
        "app.api.routes.shipping.tracking.crud_shipping_route_tracking_consolidation.get_consolidations_for_route",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.api.routes.shipping.tracking.crud_status_definition.get_by_entity",
        AsyncMock(return_value=[completed_status, in_progress_status]),
    )

    response = client.get(f"/api/v1/shipping/tracking/order/{order_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "in_progress"
    assert payload["current_route_sequence"] == 2
