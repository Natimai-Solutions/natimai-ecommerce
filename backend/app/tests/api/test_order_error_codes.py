from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.routes import order as order_routes
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.user.models.user import User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _user(*, is_superuser: bool) -> User:
    return cast(User, SimpleNamespace(id=uuid4(), is_superuser=is_superuser))


@pytest.mark.anyio
async def test_order_read_returns_order_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    order_id = uuid4()
    current_user = _user(is_superuser=False)

    monkeypatch.setattr(
        crud_order,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("order missing")),
    )

    endpoint = order_routes.router.generate_read_endpoint()

    with pytest.raises(AppError) as exc_info:
        await endpoint(session=session, id=order_id, current_user=current_user)

    assert exc_info.value.code == "order.not_found"
    assert exc_info.value.status_code == 404
    assert exc_info.value.details == {"order_id": str(order_id)}


@pytest.mark.anyio
async def test_order_read_returns_order_not_owned_for_foreign_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    order_id = uuid4()
    current_user = _user(is_superuser=False)
    foreign_order = SimpleNamespace(user_id=uuid4())

    monkeypatch.setattr(
        crud_order,
        "read",
        AsyncMock(return_value=foreign_order),
    )

    endpoint = order_routes.router.generate_read_endpoint()

    with pytest.raises(AppError) as exc_info:
        await endpoint(session=session, id=order_id, current_user=current_user)

    assert exc_info.value.code == "order.not_found"
    assert exc_info.value.status_code == 404
    assert exc_info.value.details == {"order_id": str(order_id)}


@pytest.mark.anyio
async def test_get_orders_by_status_returns_order_status_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    status_id = uuid4()
    current_user = _user(is_superuser=True)

    monkeypatch.setattr(
        crud_order_status,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("status missing")),
    )
    get_by_status_mock = AsyncMock()
    monkeypatch.setattr(crud_order, "get_by_status", get_by_status_mock)

    with pytest.raises(AppError) as exc_info:
        await order_routes.get_orders_by_status(
            session=session,
            current_user=current_user,
            order_status_id=status_id,
        )

    assert exc_info.value.code == "order.status.not_found"
    assert exc_info.value.status_code == 404
    assert exc_info.value.details == {"status_name": str(status_id)}
    get_by_status_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_get_orders_by_status_returns_order_admin_required_for_non_admin() -> (
    None
):
    session = AsyncMock()
    status_id = uuid4()
    current_user = _user(is_superuser=False)

    with pytest.raises(AppError) as exc_info:
        await order_routes.get_orders_by_status(
            session=session,
            current_user=current_user,
            order_status_id=status_id,
        )

    assert exc_info.value.code == "order.admin_required"
    assert exc_info.value.status_code == 403
    assert exc_info.value.details == {"resource": "order.status"}


@pytest.mark.anyio
async def test_order_update_returns_order_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    order_id = uuid4()
    # Writes are superuser-only since the gating pass; the not-found contract
    # is therefore asserted from an admin's seat.
    current_user = _user(is_superuser=True)

    monkeypatch.setattr(
        crud_order,
        "update",
        AsyncMock(side_effect=RecordNotFoundError("order missing")),
    )

    endpoint = order_routes.router.generate_update_endpoint()

    with pytest.raises(AppError) as exc_info:
        await endpoint(
            session=session,
            id=order_id,
            data=SimpleNamespace(),
            current_user=current_user,
        )

    assert exc_info.value.code == "order.not_found"
    assert exc_info.value.status_code == 404
    assert exc_info.value.details == {"order_id": str(order_id)}


@pytest.mark.anyio
async def test_order_delete_returns_order_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    order_id = uuid4()
    current_user = _user(is_superuser=True)

    monkeypatch.setattr(
        crud_order,
        "delete",
        AsyncMock(side_effect=RecordNotFoundError("order missing")),
    )

    endpoint = order_routes.router.generate_delete_endpoint()

    with pytest.raises(AppError) as exc_info:
        await endpoint(session=session, id=order_id, current_user=current_user)

    assert exc_info.value.code == "order.not_found"
    assert exc_info.value.status_code == 404
    assert exc_info.value.details == {"order_id": str(order_id)}


@pytest.mark.anyio
async def test_get_user_orders_returns_order_not_owned_for_foreign_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    user_id = uuid4()
    current_user = _user(is_superuser=False)
    get_by_user_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(crud_order, "get_by_user", get_by_user_mock)

    with pytest.raises(AppError) as exc_info:
        await order_routes.get_user_orders(
            session=session,
            current_user=current_user,
            user_id=user_id,
        )

    assert exc_info.value.code == "order.not_found"
    assert exc_info.value.status_code == 404
    assert exc_info.value.details == {"user_id": str(user_id)}
    get_by_user_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_order_update_requires_superuser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gating regression guard: customers must never mutate orders directly."""
    session = AsyncMock()
    order_id = uuid4()
    current_user = _user(is_superuser=False)

    update_mock = AsyncMock()
    monkeypatch.setattr(crud_order, "update", update_mock)

    endpoint = order_routes.router.generate_update_endpoint()

    with pytest.raises(AppError) as exc_info:
        await endpoint(
            session=session,
            id=order_id,
            data=SimpleNamespace(),
            current_user=current_user,
        )

    assert exc_info.value.status_code == 403
    update_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_order_delete_requires_superuser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    order_id = uuid4()
    current_user = _user(is_superuser=False)

    delete_mock = AsyncMock()
    monkeypatch.setattr(crud_order, "delete", delete_mock)

    endpoint = order_routes.router.generate_delete_endpoint()

    with pytest.raises(AppError) as exc_info:
        await endpoint(session=session, id=order_id, current_user=current_user)

    assert exc_info.value.status_code == 403
    delete_mock.assert_not_awaited()
