from decimal import Decimal
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
    assert "payment.webhook_received" in types


def _make_order(status_id: Any = None, total_amount: Decimal | None = None) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        order_status_id=status_id,
        total_amount=total_amount if total_amount is not None else Decimal("100.00"),
    )


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
    monkeypatch.setattr(
        handlers.crud_payment,
        "read",
        AsyncMock(
            return_value=SimpleNamespace(amount=order.total_amount, currency="XPF")
        ),
    )

    paid_status = _make_status("Paid")
    monkeypatch.setattr(
        handlers.crud_order_status,
        "get_by_name",
        AsyncMock(return_value=paid_status),
    )

    # The stock confirmation reads real movements through the CRUD layer,
    # which an AsyncMock session cannot serve — mock it at the service boundary.
    confirm_stock = AsyncMock(return_value=0)
    monkeypatch.setattr(handlers, "confirm_order_stock", confirm_stock)

    payload = {
        "payment_id": str(uuid4()),
        "order_id": str(order.id),
        "provider_code": "manual_check",
    }

    await handlers.on_payment_captured(cast(Any, session), payload)

    assert order.order_status_id == paid_status.id
    confirm_stock.assert_awaited_once_with(session, order_id=order.id)
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_payment_captured_handler_parks_order_on_amount_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A captured payment that does not cover the order total must never flip
    the order to Paid nor consume the reserved stock.

    Returning silently was not enough: the outbox marks the delivery processed
    and never replays it, so the incident has to be visible somewhere. The order
    is parked in PaymentReview and the admins are notified.
    """
    session = AsyncMock()
    session.add = Mock()

    order = _make_order(total_amount=Decimal("100.00"))
    monkeypatch.setattr(handlers.crud_order, "read", AsyncMock(return_value=order))
    monkeypatch.setattr(
        handlers.crud_payment,
        "read",
        AsyncMock(return_value=SimpleNamespace(amount=Decimal("1.00"), currency="XPF")),
    )

    review_status = _make_status(handlers.ORDER_STATUS_PAYMENT_REVIEW)
    status_mock = AsyncMock(return_value=review_status)
    monkeypatch.setattr(handlers.crud_order_status, "get_by_name", status_mock)

    confirm_stock = AsyncMock(return_value=0)
    monkeypatch.setattr(handlers, "confirm_order_stock", confirm_stock)
    release_stock = AsyncMock(return_value=0)
    monkeypatch.setattr(handlers, "release_order_stock", release_stock)

    notify = AsyncMock(return_value=None)
    monkeypatch.setattr(handlers, "send_payment_event_notifications", notify)

    payload = {
        "payment_id": str(uuid4()),
        "order_id": str(order.id),
        "provider_code": "payzen",
    }

    await handlers.on_payment_captured(cast(Any, session), payload)

    # Parked for human arbitration, not Paid.
    status_mock.assert_awaited_once_with(session, name="PaymentReview")
    assert order.order_status_id == review_status.id

    # Reservations stay PENDING: not confirmed (unfulfillable) and not released
    # (the customer has paid).
    confirm_stock.assert_not_awaited()
    release_stock.assert_not_awaited()

    # The admins get told, since nothing will replay this event.
    notify.assert_awaited_once()
    assert notify.await_args is not None
    assert notify.await_args.kwargs["event_type"] == "payment.amount_mismatch"
    notified = notify.await_args.kwargs["payload"]
    assert notified["amount"] == "1.00"
    assert "100.00" in notified["reason"]


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

    # Same as the captured test: the stock release needs a real session.
    release_stock = AsyncMock(return_value=0)
    monkeypatch.setattr(handlers, "release_order_stock", release_stock)

    payload = {
        "payment_id": str(uuid4()),
        "order_id": str(order.id),
        "provider_code": "manual_transfer",
        "reason": "no funds",
    }

    await handlers.on_payment_rejected(cast(Any, session), payload)

    assert order.order_status_id == failed_status.id
    release_stock.assert_awaited_once_with(session, order_id=order.id)
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


@pytest.mark.anyio
async def test_payment_webhook_received_handler_dispatches_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notify_mock = AsyncMock()
    monkeypatch.setattr(handlers, "send_payment_event_notifications", notify_mock)

    session = AsyncMock()
    payload = {
        "payment_id": str(uuid4()),
        "order_id": str(uuid4()),
        "provider_code": "payzen",
        "user_id": str(uuid4()),
    }

    await handlers.on_payment_webhook_received(cast(Any, session), payload)

    notify_mock.assert_awaited_once_with(
        session=session,
        event_type="payment.webhook_received",
        payload=payload,
    )


@pytest.mark.anyio
async def test_payment_captured_notification_handler_dispatches_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notify_mock = AsyncMock()
    monkeypatch.setattr(handlers, "send_payment_event_notifications", notify_mock)

    session = AsyncMock()
    payload = {
        "payment_id": str(uuid4()),
        "order_id": str(uuid4()),
        "provider_code": "manual_transfer",
        "user_id": str(uuid4()),
    }

    await handlers.on_payment_captured_notify(cast(Any, session), payload)

    notify_mock.assert_awaited_once_with(
        session=session,
        event_type="payment.captured",
        payload=payload,
    )


@pytest.mark.anyio
async def test_invoice_handler_issues_when_amounts_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: this handler called a helper that no longer existed.

    The amount guard was renamed (_captured_amount_covers_order ->
    _captured_amount_mismatch, with inverted semantics) while the invoicing
    handler was written on another branch against the old name. The merge kept
    both, so every payment.captured raised NameError at call time and no
    invoice was ever issued — the module still imported fine, and no test
    exercised this handler.
    """
    session = AsyncMock()
    session.add = Mock()

    order = _make_order(total_amount=Decimal("100.00"))
    monkeypatch.setattr(handlers.crud_order, "read", AsyncMock(return_value=order))
    monkeypatch.setattr(
        handlers.crud_payment,
        "read",
        AsyncMock(
            return_value=SimpleNamespace(amount=Decimal("100.00"), currency="XPF")
        ),
    )
    issue = AsyncMock(return_value=SimpleNamespace(invoice_number="FA-2026-0001"))
    monkeypatch.setattr(handlers, "issue_invoice_for_order", issue)

    await handlers.on_payment_captured_issue_invoice(
        cast(Any, session),
        {"payment_id": str(uuid4()), "order_id": str(order.id)},
    )

    issue.assert_awaited_once_with(session, order_id=order.id)


@pytest.mark.anyio
async def test_invoice_handler_skips_on_amount_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An order whose capture does not cover its total must not be invoiced."""
    session = AsyncMock()
    session.add = Mock()

    order = _make_order(total_amount=Decimal("100.00"))
    monkeypatch.setattr(handlers.crud_order, "read", AsyncMock(return_value=order))
    monkeypatch.setattr(
        handlers.crud_payment,
        "read",
        AsyncMock(return_value=SimpleNamespace(amount=Decimal("1.00"), currency="XPF")),
    )
    issue = AsyncMock()
    monkeypatch.setattr(handlers, "issue_invoice_for_order", issue)

    await handlers.on_payment_captured_issue_invoice(
        cast(Any, session),
        {"payment_id": str(uuid4()), "order_id": str(order.id)},
    )

    issue.assert_not_awaited()
