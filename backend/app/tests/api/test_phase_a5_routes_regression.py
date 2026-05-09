import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.api.routes.address as address_routes
import app.api.routes.shipping.tracking as tracking_routes
import app.api.routes.user_notification as notification_routes
import app.api.routes.user_review as review_routes
from app.api.deps import get_current_user
from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.shipping.models.route_tracking import ShippingRouteTracking
from app.features.user.models.address import Address
from app.features.user.models.notification import Notification, UserNotification
from app.features.user.models.review import Review
from app.main import app


@pytest.fixture
def current_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, is_active=True)


@pytest.fixture(autouse=True)
def override_dependencies(current_user: SimpleNamespace):
    async def _override_current_user() -> SimpleNamespace:
        return current_user

    async def _override_get_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_current_user] = _override_current_user
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
    monkeypatch.setattr(address_routes.crud_address, "read", read_mock)

    response = client.get(f"/api/v1/address/users/{user_id}/addresses/{address_id}")

    assert response.status_code == 200
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
    monkeypatch.setattr(review_routes.crud_review, "read", read_mock)
    monkeypatch.setattr(review_routes.crud_review, "update", update_mock)

    response = client.patch(
        f"/api/v1/review/users/{user_id}/reviews/{review_id}",
        json={"rating": 5, "comment": "much better"},
    )

    assert response.status_code == 200

    read_kwargs = read_mock.await_args.kwargs
    assert read_kwargs["id"] == review_id

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
        notification_routes.crud_user_notification,
        "get_by_user_and_notification",
        relation_mock,
    )
    monkeypatch.setattr(notification_routes.crud_notification, "read", read_mock)

    response = client.get(
        f"/api/v1/notification/users/{user_id}/notifications/{notification_id}"
    )

    assert response.status_code == 200

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
        notification_routes.crud_user_notification,
        "get_by_user_and_notification",
        relation_mock,
    )
    monkeypatch.setattr(
        notification_routes.crud_user_notification, "delete", delete_mock
    )

    response = client.delete(
        f"/api/v1/notification/users/{user_id}/notifications/{notification_id}"
    )

    assert response.status_code == 204

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
        selected_at=datetime.now(timezone.utc),
        sequence_order=1,
    )

    update_status_mock = AsyncMock(return_value=tracking)
    monkeypatch.setattr(
        tracking_routes.shipping_route_tracking_router.crud,
        "update_status",
        update_status_mock,
    )

    response = client.post(
        f"/api/v1/shipping/tracking/{tracking_id}/update-status",
        json={"new_status_id": str(new_status_id), "reason": "manual fix"},
    )

    assert response.status_code == 200

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
    assert response.json()["detail"] == "Tracking not found"
