import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.api.routes.product as product_routes
import app.api.routes.shipping.tracking as tracking_routes
from app.api.deps import get_current_user, get_current_user_optional
from app.core.db import get_db
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.shipping.models.route_tracking import ShippingRouteTracking
from app.features.user.crud.address import crud_address
from app.features.user.crud.notification import (
    crud_notification,
    crud_user_notification,
)
from app.features.user.crud.review import crud_review
from app.features.user.models.address import Address
from app.features.user.models.notification import Notification, UserNotification
from app.features.user.models.review import Review
from app.features.user.models.user import User
from app.main import app


@pytest.fixture
def current_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)


@pytest.fixture(autouse=True)
def override_dependencies(current_user: SimpleNamespace) -> Generator[None, None, None]:
    async def _override_current_user() -> SimpleNamespace:
        return current_user

    async def _override_current_user_optional() -> SimpleNamespace:
        return current_user

    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        # commit is awaited by routes that persist an outbox event after the
        # CRUD's own commit (e.g. tracking update-status).
        yield SimpleNamespace(commit=AsyncMock())

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_current_user_optional] = (
        _override_current_user_optional
    )
    app.dependency_overrides[get_db] = _override_get_db

    yield

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_address_get_uses_read_with_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    user_id = current_user.id
    address_id = uuid.uuid4()

    address = Address(
        id=address_id,
        user_id=user_id,
        street="1 Main Street",
        city="Papeete",
        state=None,
        postal_code="98714",
        country="PF",
        type="shipping",
    )

    read_mock = AsyncMock(return_value=address)
    monkeypatch.setattr(crud_address, "read", read_mock)

    response = client.get(f"/api/v1/address/users/{user_id}/addresses/{address_id}")

    assert response.status_code == 200
    assert read_mock.await_args is not None
    read_kwargs = read_mock.await_args.kwargs
    assert read_kwargs["id"] == address_id


@pytest.mark.asyncio
async def test_review_update_uses_read_then_update_with_id_and_record(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    user_id = current_user.id
    review_id = uuid.uuid4()
    product_id = uuid.uuid4()

    review = Review(
        id=review_id,
        user_id=user_id,
        product_id=product_id,
        rating=3,
        comment="ok",
    )
    updated_review = Review(
        id=review_id,
        user_id=user_id,
        product_id=product_id,
        rating=5,
        comment="much better",
    )

    read_mock = AsyncMock(return_value=review)
    update_mock = AsyncMock(return_value=updated_review)
    monkeypatch.setattr(crud_review, "read", read_mock)
    monkeypatch.setattr(crud_review, "update", update_mock)

    response = client.patch(
        f"/api/v1/review/users/{user_id}/reviews/{review_id}",
        json={"rating": 5, "comment": "much better"},
    )

    assert response.status_code == 200

    assert read_mock.await_args is not None
    read_kwargs = read_mock.await_args.kwargs
    assert read_kwargs["id"] == review_id

    assert update_mock.await_args is not None
    update_kwargs = update_mock.await_args.kwargs
    assert update_kwargs["id"] == review_id
    assert update_kwargs["record"] is review
    assert update_kwargs["data"].rating == 5
    assert update_kwargs["data"].comment == "much better"


@pytest.mark.asyncio
async def test_notification_get_uses_read_with_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    user_id = current_user.id
    notification_id = uuid.uuid4()

    user_notification = UserNotification(
        id=uuid.uuid4(),
        user_id=user_id,
        notification_id=notification_id,
        is_read=False,
    )
    notification = Notification(
        id=notification_id,
        title="Order update",
        content="Your order is shipped",
        type="order_status_update",
        priority=2,
    )

    relation_mock = AsyncMock(return_value=user_notification)
    read_mock = AsyncMock(return_value=notification)

    monkeypatch.setattr(
        crud_user_notification,
        "get_by_user_and_notification",
        relation_mock,
    )
    monkeypatch.setattr(crud_notification, "read", read_mock)

    response = client.get(
        f"/api/v1/notification/users/{user_id}/notifications/{notification_id}"
    )

    assert response.status_code == 200

    assert read_mock.await_args is not None
    read_kwargs = read_mock.await_args.kwargs
    assert read_kwargs["id"] == notification_id


@pytest.mark.asyncio
async def test_notification_delete_uses_delete_with_id_and_record(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    user_id = current_user.id
    notification_id = uuid.uuid4()

    user_notification = UserNotification(
        id=uuid.uuid4(),
        user_id=user_id,
        notification_id=notification_id,
        is_read=False,
    )

    relation_mock = AsyncMock(return_value=user_notification)
    delete_mock = AsyncMock(return_value=True)

    monkeypatch.setattr(
        crud_user_notification,
        "get_by_user_and_notification",
        relation_mock,
    )
    monkeypatch.setattr(crud_user_notification, "delete", delete_mock)

    response = client.delete(
        f"/api/v1/notification/users/{user_id}/notifications/{notification_id}"
    )

    assert response.status_code == 204

    assert delete_mock.await_args is not None
    delete_kwargs = delete_mock.await_args.kwargs
    assert delete_kwargs["id"] == user_notification.id
    assert delete_kwargs["record"] is user_notification


@pytest.mark.asyncio
async def test_tracking_update_status_passes_harmonized_signature(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    tracking_id = uuid.uuid4()
    new_status_id = uuid.uuid4()

    tracking = ShippingRouteTracking(
        id=tracking_id,
        order_id=uuid.uuid4(),
        route_id=uuid.uuid4(),
        status_id=new_status_id,
        address_id=uuid.uuid4(),
        selected_at=datetime.now(UTC),
        sequence_order=1,
    )

    update_status_mock = AsyncMock(return_value=tracking)
    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "update_status",
        update_status_mock,
    )

    # The route resolves the new status code and publishes a
    # tracking.status_changed outbox event. Stub both collaborators (string
    # targets keep mypy's implicit-reexport check happy).
    status_def = SimpleNamespace(id=new_status_id, code="shipped", name="Expédié")
    monkeypatch.setattr(
        "app.api.routes.shipping.tracking.crud_status_definition.get_by_entity",
        AsyncMock(return_value=[status_def]),
    )
    publish_mock = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.shipping.tracking.outbox_registry.publish", publish_mock
    )

    response = client.post(
        f"/api/v1/shipping/tracking/{tracking_id}/update-status",
        json={"new_status_id": str(new_status_id), "reason": "manual fix"},
    )

    assert response.status_code == 200

    # The outbox event carries the resolved status code and correlation id.
    assert publish_mock.await_args is not None
    publish_kwargs = publish_mock.await_args.kwargs
    assert publish_kwargs["event_type"] == "tracking.status_changed"
    assert publish_kwargs["payload"]["status_code"] == "shipped"
    assert publish_kwargs["correlation_id"] == tracking_id

    assert update_status_mock.await_args is not None
    update_kwargs = update_status_mock.await_args.kwargs
    assert update_kwargs["tracking_id"] == tracking_id
    assert update_kwargs["new_status_id"] == new_status_id
    assert update_kwargs["changed_by"] == str(current_user.id)
    assert update_kwargs["reason"] == "manual fix"


@pytest.mark.asyncio
async def test_tracking_update_status_maps_record_not_found_to_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracking_id = uuid.uuid4()
    new_status_id = uuid.uuid4()

    update_status_mock = AsyncMock(side_effect=RecordNotFoundError("not found"))
    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "update_status",
        update_status_mock,
    )

    response = client.post(
        f"/api/v1/shipping/tracking/{tracking_id}/update-status",
        json={"new_status_id": str(new_status_id)},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "shipping.tracking.not_found"
    assert response.json()["error"]["details"] == {"tracking_id": str(tracking_id)}


@pytest.mark.asyncio
async def test_tracking_update_status_maps_value_error_to_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracking_id = uuid.uuid4()
    new_status_id = uuid.uuid4()

    update_status_mock = AsyncMock(side_effect=ValueError("Transition not allowed"))
    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "update_status",
        update_status_mock,
    )

    response = client.post(
        f"/api/v1/shipping/tracking/{tracking_id}/update-status",
        json={"new_status_id": str(new_status_id)},
    )

    assert response.status_code == 400
    payload = response.json()["error"]
    assert payload["code"] == "shipping.tracking.invalid_transition"
    assert payload["details"] == {
        "tracking_id": str(tracking_id),
        "reason": "Transition not allowed",
    }


@pytest.mark.asyncio
async def test_activate_next_route_maps_value_error_to_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracking_id = uuid.uuid4()

    activate_next_route_mock = AsyncMock(
        side_effect=ValueError("No active segment to activate")
    )
    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "activate_next_route",
        activate_next_route_mock,
    )

    response = client.post(
        f"/api/v1/shipping/tracking/{tracking_id}/activate-next-route"
    )

    assert response.status_code == 400
    payload = response.json()["error"]
    assert payload["code"] == "shipping.tracking.invalid_transition"
    assert payload["details"] == {
        "tracking_id": str(tracking_id),
        "reason": "No active segment to activate",
    }


@pytest.mark.asyncio
async def test_tracking_update_status_requires_superuser(
    client: TestClient,
    current_user: SimpleNamespace,
) -> None:
    current_user.is_superuser = False
    tracking_id = uuid.uuid4()
    new_status_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/shipping/tracking/{tracking_id}/update-status",
        json={"new_status_id": str(new_status_id)},
    )

    assert response.status_code == 403
    payload = response.json()["error"]
    assert payload["code"] == "auth.superuser.required"
    assert "enough privileges" in payload["message"]


@pytest.mark.asyncio
async def test_read_multi_rejects_raw_filter_query_string(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/address/?filter=id%20is%20not%20null",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400
    payload = response.json()["error"]
    assert payload["code"] == "resource.filter.unsupported"
    assert "Raw string filters" in payload["message"]


@pytest.mark.asyncio
async def test_product_router_create_permission_requires_superuser(
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    current_user.is_superuser = False

    permission_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        product_routes.router.crud,
        "check_user_permission",
        permission_mock,
    )
    session = cast(Any, AsyncMock())

    with pytest.raises(AppError) as exc_info:
        await product_routes.router._check_auth(
            session,
            "create",
            cast(User, current_user),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "resource.superuser_required"
    assert "Superuser privileges required" in exc_info.value.message
    permission_mock.assert_not_awaited()
