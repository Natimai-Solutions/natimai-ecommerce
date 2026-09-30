"""Tests for the payment.captured → supplier purchase orders handler guards."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.handlers.supplier_purchase_orders as handler


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_handler_skips_invalid_order_id(monkeypatch: pytest.MonkeyPatch) -> None:
    process_spy = AsyncMock()
    monkeypatch.setattr(handler, "process_purchase_orders", process_spy)

    await handler.on_payment_captured_create_supplier_orders(
        MagicMock(), {"order_id": "not-a-uuid"}
    )

    process_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_handler_delegates_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
    process_spy = AsyncMock()
    monkeypatch.setattr(handler, "process_purchase_orders", process_spy)

    order_id = uuid.uuid4()
    session = MagicMock()
    session.get = AsyncMock(return_value=SimpleNamespace(grouped_departure_id=None))
    await handler.on_payment_captured_create_supplier_orders(
        session, {"order_id": str(order_id)}
    )

    process_spy.assert_awaited_once_with(session, order_id)


@pytest.mark.anyio
async def test_handler_skips_orders_attached_to_a_grouped_departure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grouped orders are bought with their departure, never one PO each."""
    process_spy = AsyncMock()
    monkeypatch.setattr(handler, "process_purchase_orders", process_spy)

    session = MagicMock()
    session.get = AsyncMock(
        return_value=SimpleNamespace(grouped_departure_id=uuid.uuid4())
    )
    await handler.on_payment_captured_create_supplier_orders(
        session, {"order_id": str(uuid.uuid4())}
    )

    process_spy.assert_not_awaited()
