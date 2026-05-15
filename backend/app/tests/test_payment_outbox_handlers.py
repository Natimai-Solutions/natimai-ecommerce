from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.handlers import payment as handlers
from app.outbox.registry import outbox_registry


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_payment_handlers_registered() -> None:
    types = outbox_registry.list_event_types()
    assert "payment.awaiting_validation" in types
    assert "payment.captured" in types
    assert "payment.rejected" in types


def _make_order(status_id: Any = None) -> Any:
    return SimpleNamespace(id=uuid4(), order_status_id=status_id)


def _make_status(name: str) -> Any:
    return SimpleNamespace(id=uuid4(), name=name)


@pytest.mark.anyio
async def test_payment_captured_handler_syncs_order_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    order = _make_order()
    monkeypatch.setattr(handlers.crud_order, "read", AsyncMock(return_value=order))

    paid_status = _make_status("Paid")
    monkeypatch.setattr(
        handlers.crud_order_status,
        "get_by_name",
        AsyncMock(return_value=paid_status),
    )

    payload = {
        "payment_id": str(uuid4()),
        "order_id": str(order.id),
        "provider_code": "manual_check",
    }

    await handlers.on_payment_captured(cast(Any, session), payload)

    assert order.order_status_id == paid_status.id
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_payment_rejected_handler_syncs_order_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    order = _make_order()
    monkeypatch.setattr(handlers.crud_order, "read", AsyncMock(return_value=order))

    failed_status = _make_status("PaymentFailed")
    monkeypatch.setattr(
        handlers.crud_order_status,
        "get_by_name",
        AsyncMock(return_value=failed_status),
    )

    payload = {
        "payment_id": str(uuid4()),
        "order_id": str(order.id),
        "provider_code": "manual_transfer",
        "reason": "no funds",
    }

    await handlers.on_payment_rejected(cast(Any, session), payload)

    assert order.order_status_id == failed_status.id
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_payment_awaiting_validation_handler_syncs_order_awaiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    order = _make_order()
    monkeypatch.setattr(handlers.crud_order, "read", AsyncMock(return_value=order))

    awaiting_status = _make_status("AwaitingPayment")
    monkeypatch.setattr(
        handlers.crud_order_status,
        "get_by_name",
        AsyncMock(return_value=awaiting_status),
    )

    payload = {
        "payment_id": str(uuid4()),
        "order_id": str(order.id),
        "provider_code": "manual_check",
    }

    await handlers.on_payment_awaiting_validation(cast(Any, session), payload)

    assert order.order_status_id == awaiting_status.id


@pytest.mark.anyio
async def test_payment_handler_skips_when_no_order_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    read_mock = AsyncMock()
    monkeypatch.setattr(handlers.crud_order, "read", read_mock)

    payload = {
        "payment_id": str(uuid4()),
        "order_id": None,
        "provider_code": "manual_check",
    }

    await handlers.on_payment_captured(cast(Any, session), payload)

    read_mock.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_payment_handler_skips_on_invalid_order_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    read_mock = AsyncMock()
    monkeypatch.setattr(handlers.crud_order, "read", read_mock)

    payload = {
        "payment_id": str(uuid4()),
        "order_id": "not-a-uuid",
        "provider_code": "manual_check",
    }

    await handlers.on_payment_captured(cast(Any, session), payload)

    read_mock.assert_not_awaited()
