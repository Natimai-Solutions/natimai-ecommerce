"""Inbound Ingram order-status webhook (Q3).

The endpoint is unauthenticated by design at the transport level — it is
reachable from the internet and guarded only by a Bearer secret. That makes its
auth branches worth pinning: a webhook that accepts unsigned calls would let
anyone mark supplier orders as shipped, which fires customer emails and moves
the tracking forward.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes.webhooks import (
    _parse_estimated_delivery,
    ingram_order_status_webhook,
)
from app.core.config import settings
from app.features.integrations.models.supplier_order import SupplierOrderStatus


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "INGRAM_WEBHOOK_SECRET", "s3cret")


def _request(body: Any, *, token: str | None = "s3cret") -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    request = MagicMock()
    request.headers = headers
    if isinstance(body, Exception):
        request.json = AsyncMock(side_effect=body)
    else:
        request.json = AsyncMock(return_value=body)
    return request


def _session(supplier_order: Any = None) -> Any:
    result = MagicMock()
    result.first = MagicMock(return_value=supplier_order)
    session = MagicMock()
    session.exec = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _supplier_order(status: SupplierOrderStatus) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        local_order_id=uuid.uuid4(),
        supplier_name="ingram",
        supplier_order_number="ING-1",
        customer_order_number="CMD-2026-00042",
        status=status,
        supplier_status_label=None,
        estimated_delivery=None,
    )


@pytest.mark.anyio
async def test_unconfigured_secret_refuses_instead_of_accepting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing configuration must not degrade into an open endpoint."""
    monkeypatch.setattr(settings, "INGRAM_WEBHOOK_SECRET", None)

    response = await ingram_order_status_webhook(_request({}), _session())

    assert response.status_code == 503


@pytest.mark.anyio
async def test_a_wrong_or_absent_token_is_rejected() -> None:
    for token in (None, "", "wrong", "s3cre"):
        response = await ingram_order_status_webhook(
            _request({"ingramOrderNumber": "ING-1"}, token=token), _session()
        )
        assert response.status_code == 401, token


@pytest.mark.anyio
async def test_malformed_payloads_are_rejected() -> None:
    bad_json = await ingram_order_status_webhook(
        _request(ValueError("not json")), _session()
    )
    assert bad_json.status_code == 400

    no_identifier = await ingram_order_status_webhook(
        _request({"orderStatus": "shipped"}), _session()
    )
    assert no_identifier.status_code == 400


@pytest.mark.anyio
async def test_an_unknown_order_is_acknowledged_not_retried() -> None:
    """200, deliberately: Ingram would otherwise retry forever a callback for
    an order this system has no record of."""
    response = await ingram_order_status_webhook(
        _request({"ingramOrderNumber": "ING-unknown", "orderStatus": "shipped"}),
        _session(supplier_order=None),
    )

    assert response.status_code == 200


@pytest.mark.anyio
async def test_a_shipment_updates_the_order_and_publishes_the_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = AsyncMock()
    monkeypatch.setattr("app.api.routes.webhooks.outbox_registry.publish", publish)
    order = _supplier_order(SupplierOrderStatus.SUBMITTED)
    session = _session(order)

    await ingram_order_status_webhook(
        _request(
            {
                "ingramOrderNumber": "ING-1",
                "orderStatus": "Shipped",
                "estimatedDeliveryDate": "2026-09-15",
            }
        ),
        session,
    )

    assert order.supplier_status_label == "shipped"
    assert order.estimated_delivery == datetime(2026, 9, 15, tzinfo=UTC)
    publish.assert_awaited_once()
    assert publish.await_args is not None
    assert publish.await_args.kwargs["event_type"] == "supplier_order.shipped"
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_a_repeated_shipment_callback_does_not_re_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingram retries callbacks, and nothing moves the order off SUBMITTED, so
    the event must be gated on the *transition* — recorded by the previously
    stored label, the only trace that the shipment was already seen."""
    publish = AsyncMock()
    monkeypatch.setattr("app.api.routes.webhooks.outbox_registry.publish", publish)
    order = _supplier_order(SupplierOrderStatus.SUBMITTED)

    # First callback: the transition.
    await ingram_order_status_webhook(
        _request({"ingramOrderNumber": "ING-1", "orderStatus": "Shipped"}),
        _session(order),
    )
    assert publish.await_count == 1

    # Retry of the same callback: nothing new to announce.
    await ingram_order_status_webhook(
        _request({"ingramOrderNumber": "ING-1", "orderStatus": "Shipped"}),
        _session(order),
    )
    assert publish.await_count == 1

    # A later, different shipped label ("in transit") is still the same
    # milestone and must not re-announce either.
    await ingram_order_status_webhook(
        _request({"ingramOrderNumber": "ING-1", "orderStatus": "In Transit"}),
        _session(order),
    )
    assert publish.await_count == 1


@pytest.mark.anyio
async def test_a_non_shipping_status_only_records_the_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = AsyncMock()
    monkeypatch.setattr("app.api.routes.webhooks.outbox_registry.publish", publish)
    order = _supplier_order(SupplierOrderStatus.SUBMITTED)

    await ingram_order_status_webhook(
        _request({"ingramOrderNumber": "ING-1", "orderStatus": "Backordered"}),
        _session(order),
    )

    assert order.supplier_status_label == "backordered"
    publish.assert_not_awaited()


def test_delivery_dates_accept_ingram_s_formats() -> None:
    assert _parse_estimated_delivery("2026-09-15") == datetime(2026, 9, 15, tzinfo=UTC)
    assert _parse_estimated_delivery("2026-09-15T10:30:00Z") == datetime(
        2026, 9, 15, 10, 30, tzinfo=UTC
    )
    # An unparseable or absent date must not sink the whole callback.
    assert _parse_estimated_delivery("15/09/2026") is None
    assert _parse_estimated_delivery(None) is None
    # Naive datetimes are assumed UTC rather than silently compared as naive.
    assert _parse_estimated_delivery(datetime(2026, 9, 15)) == datetime(
        2026, 9, 15, tzinfo=UTC
    )
