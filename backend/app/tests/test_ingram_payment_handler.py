"""Tests for the payment.captured → Ingram PO outbox handler guards."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.handlers.ingram_micro as handler
from app.core.config import settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_handler_noop_when_feature_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "INGRAM_ORDER_CREATION_ENABLED", False)
    process_spy = AsyncMock()
    monkeypatch.setattr(handler, "process_ingram_purchase_order", process_spy)

    await handler.on_payment_captured_create_ingram_order(
        MagicMock(), {"order_id": str(uuid.uuid4())}
    )

    process_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_handler_skips_invalid_order_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "INGRAM_ORDER_CREATION_ENABLED", True)
    process_spy = AsyncMock()
    monkeypatch.setattr(handler, "process_ingram_purchase_order", process_spy)

    await handler.on_payment_captured_create_ingram_order(
        MagicMock(), {"order_id": "not-a-uuid"}
    )

    process_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_handler_delegates_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "INGRAM_ORDER_CREATION_ENABLED", True)
    process_spy = AsyncMock()
    monkeypatch.setattr(handler, "process_ingram_purchase_order", process_spy)

    order_id = uuid.uuid4()
    session = MagicMock()
    await handler.on_payment_captured_create_ingram_order(
        session, {"order_id": str(order_id)}
    )

    process_spy.assert_awaited_once_with(session, order_id)
