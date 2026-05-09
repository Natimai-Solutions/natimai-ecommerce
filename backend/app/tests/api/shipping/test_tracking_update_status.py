import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.shipping.crud.route_tracking import ShippingRouteTrackingCrud
from app.features.shipping.models.route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingCreate,
    ShippingRouteTrackingUpdate,
)


def _build_crud() -> ShippingRouteTrackingCrud:
    return ShippingRouteTrackingCrud(
        model=ShippingRouteTracking,
        schema_create=ShippingRouteTrackingCreate,
        schema_update=ShippingRouteTrackingUpdate,
    )


@pytest.mark.asyncio
async def test_update_status_accepts_new_status_id() -> None:
    crud = _build_crud()

    tracking_id = uuid.uuid4()
    old_status = SimpleNamespace(id=uuid.uuid4(), code="pending")
    new_status_id = uuid.uuid4()
    new_status = SimpleNamespace(
        id=new_status_id,
        code="in_progress",
        entity="route_tracking",
        is_active=True,
    )

    tracking = SimpleNamespace(id=tracking_id, status=old_status)
    updated_tracking = SimpleNamespace(id=tracking_id, status=new_status)
    session = AsyncMock()
    session.get = AsyncMock(return_value=new_status)

    crud.read = AsyncMock(return_value=tracking)
    crud.validate_status_transition = AsyncMock(return_value=True)
    crud.get_status_transition = AsyncMock(return_value=None)
    crud.update = AsyncMock(return_value=updated_tracking)
    crud.create_status_log = AsyncMock()

    changed_by = uuid.uuid4()
    result = await crud.update_status(
        session=session,
        tracking_id=tracking_id,
        new_status_id=new_status_id,
        reason="manual update",
        changed_by=changed_by,
    )

    assert result is updated_tracking
    assert session.get.await_args.args[1] == new_status_id

    update_kwargs = crud.update.await_args.kwargs
    assert update_kwargs["id"] == tracking_id
    assert update_kwargs["data"]["status_id"] == new_status_id
    assert update_kwargs["data"]["notes"] == "manual update"
    assert "last_status_update" in update_kwargs["data"]

    log_kwargs = crud.create_status_log.await_args.kwargs
    assert log_kwargs["from_status_id"] == old_status.id
    assert log_kwargs["to_status_id"] == new_status_id
    assert log_kwargs["reason"] == "manual update"
    assert log_kwargs["changed_by"] == str(changed_by)


@pytest.mark.asyncio
async def test_update_status_keeps_legacy_new_status_code() -> None:
    crud = _build_crud()

    tracking_id = uuid.uuid4()
    old_status = SimpleNamespace(id=uuid.uuid4(), code="in_progress")
    new_status = SimpleNamespace(
        id=uuid.uuid4(),
        code="completed",
        entity="route_tracking",
        is_active=True,
    )

    tracking = SimpleNamespace(id=tracking_id, status=old_status)
    updated_tracking = SimpleNamespace(id=tracking_id, status=new_status)

    crud.read = AsyncMock(return_value=tracking)
    crud.get_status_by_code = AsyncMock(return_value=new_status)
    crud.validate_status_transition = AsyncMock(return_value=True)
    crud.get_status_transition = AsyncMock(return_value=None)
    crud.update = AsyncMock(return_value=updated_tracking)
    crud.create_status_log = AsyncMock()

    result = await crud.update_status(
        session=AsyncMock(),
        tracking_id=tracking_id,
        new_status="completed",
        notes="legacy note",
    )

    assert result is updated_tracking
    crud.get_status_by_code.assert_awaited_once()

    update_kwargs = crud.update.await_args.kwargs
    assert update_kwargs["data"]["notes"] == "legacy note"

    log_kwargs = crud.create_status_log.await_args.kwargs
    assert log_kwargs["reason"] == "legacy note"


@pytest.mark.asyncio
async def test_update_status_requires_target_status() -> None:
    crud = _build_crud()

    with pytest.raises(ValueError, match="Either 'new_status_id' or 'new_status' must be provided"):
        await crud.update_status(session=AsyncMock(), tracking_id=uuid.uuid4())
