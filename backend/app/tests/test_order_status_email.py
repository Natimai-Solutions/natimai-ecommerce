"""Customer e-mail on ``order.status_changed`` (no database)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.handlers import order as handlers


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _payload(new_status: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "order_id": str(uuid4()),
        "order_number": "CMD-2026-00042",
        "user_id": str(uuid4()),
        "old_status": "Paid",
        "new_status": new_status,
        "grouped_departure_id": None,
        "reason": None,
    }
    base.update(overrides)
    return base


@pytest.fixture
def send(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(handlers, "_send_order_email", mock)
    monkeypatch.setattr(
        handlers,
        "_resolve_user_from_payload",
        AsyncMock(return_value=SimpleNamespace(full_name="Tehani", email="t@x.pf")),
    )
    return mock


@pytest.mark.anyio
async def test_fulfilment_step_is_emailed_with_the_departure(send: AsyncMock) -> None:
    departure = SimpleNamespace(
        name="Octobre",
        estimated_delivery_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=departure)

    await handlers.on_order_status_changed_customer(
        session, _payload("InTransit", grouped_departure_id=str(uuid4()))
    )

    send.assert_awaited_once()
    assert send.await_args is not None
    kwargs = send.await_args.kwargs
    assert kwargs["subject"] == "Commande CMD-2026-00042 : En transit"
    assert "Bonjour Tehani" in kwargs["text"]
    assert "Octobre" in kwargs["text"] and "10/11/2026" in kwargs["text"]
    assert "en route" in kwargs["html"]


@pytest.mark.anyio
async def test_every_fulfilment_status_has_a_message(send: AsyncMock) -> None:
    from app.features.order.services.status import FULFILLMENT_STATUSES

    assert set(FULFILLMENT_STATUSES) == set(handlers.ORDER_STATUS_MESSAGES)
    for status in FULFILLMENT_STATUSES:
        await handlers.on_order_status_changed_customer(AsyncMock(), _payload(status))
    assert send.await_count == len(FULFILLMENT_STATUSES)


@pytest.mark.anyio
async def test_payment_statuses_are_not_emailed_twice(send: AsyncMock) -> None:
    # Paid / refunded… already have their own e-mails: this handler stays quiet.
    for status in ("Paid", "Refunded", "AwaitingPayment"):
        await handlers.on_order_status_changed_customer(AsyncMock(), _payload(status))
    send.assert_not_awaited()
