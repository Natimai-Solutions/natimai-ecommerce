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


def _build_status(
    *,
    code: str,
    is_terminal: bool,
    is_error: bool,
) -> StatusDefinition:
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
    notes: str | None = None,
) -> ShippingRouteTracking:
    return ShippingRouteTracking(
        id=uuid4(),
        order_id=order_id,
        route_id=route_id,
        status_id=status_id,
        address_id=address_id,
        selected_at=datetime.now(timezone.utc),
        sequence_order=sequence_order,
        notes=notes,
    )


def test_derive_exception_scenarios_detects_supplier_delay() -> None:
    order_id = uuid4()
    route_id = uuid4()
    address_id = uuid4()

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
            status_id=delayed_status.id,
            sequence_order=1,
        )
    ]

    scenarios = tracking_routes._derive_order_exception_scenarios(
        trackings,
        status_by_id={
            delayed_status.id: delayed_status,
        },
    )

    assert scenarios == ["supplier_delay"]


def test_derive_exception_scenarios_detects_split_and_segment_failure() -> None:
    order_id = uuid4()
    route_id = uuid4()
    address_id = uuid4()

    in_progress_status = _build_status(
        code="in_progress",
        is_terminal=False,
        is_error=False,
    )
    failed_status = _build_status(
        code="segment_failed",
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
            status_id=failed_status.id,
            sequence_order=1,
            notes="split_colis second package",
        ),
    ]

    scenarios = tracking_routes._derive_order_exception_scenarios(
        trackings,
        status_by_id={
            in_progress_status.id: in_progress_status,
            failed_status.id: failed_status,
        },
    )

    assert scenarios == ["parcel_split", "segment_failure"]


def test_get_order_tracking_exposes_d4_exception_scenarios(
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
    delayed_status = _build_status(
        code="supplier_delayed",
        is_terminal=False,
        is_error=True,
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
    delayed_tracking = _build_tracking(
        order_id=order_id,
        route_id=route_id,
        address_id=address_id,
        status_id=delayed_status.id,
        sequence_order=2,
    )
    split_tracking = _build_tracking(
        order_id=order_id,
        route_id=route_id,
        address_id=address_id,
        status_id=in_progress_status.id,
        sequence_order=2,
        notes="split_parcel secondary leg",
    )

    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "get_by_order_id",
        AsyncMock(return_value=first_tracking),
    )
    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "get_trackings_by_order_sequence",
        AsyncMock(return_value=[first_tracking, delayed_tracking, split_tracking]),
    )
    monkeypatch.setattr(
        "app.api.routes.shipping.tracking.crud_shipping_route_tracking_consolidation.get_consolidations_for_route",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.api.routes.shipping.tracking.crud_status_definition.get_by_entity",
        AsyncMock(return_value=[completed_status, delayed_status, in_progress_status]),
    )

    response = client.get(f"/api/v1/shipping/tracking/order/{order_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "supplier_delayed"
    assert payload["current_route_sequence"] == 2
    assert payload["exception_scenarios"] == ["supplier_delay", "parcel_split"]
