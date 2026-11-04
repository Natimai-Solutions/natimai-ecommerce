from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Request

from app.api.routes.payments import (
    _publish_provider_outcome_event,
    _publish_provider_webhook_received_event,
    _sync_payment_status_for_provider_status,
    payzen_ipn,
)
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _payment_row_lock_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """The session is a stand-in here: the row lock (``FOR UPDATE``) is
    exercised against the real database (webhook pipeline integration)."""

    async def _same(_session: object, payment: object) -> object:
        return payment

    monkeypatch.setattr("app.api.routes.payments.lock_payment", _same)


@pytest.fixture(autouse=True)
def _no_webhook_journal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The session is a stand-in: the shared event journal
    (``payment_webhook_events``) is covered by test_payzen_ipn_journal.py."""

    async def _none(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.api.routes.payments.record_webhook_event", _none)


@pytest.mark.anyio
async def test_sync_payment_status_sets_completed_on_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(id=uuid4(), order_id=uuid4(), payment_status_id=None),
    )
    completed_status = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=completed_status),
    )

    await _sync_payment_status_for_provider_status(
        session=session, payment=payment, trans_status="PAID"
    )

    assert payment.payment_status_id == completed_status.id


@pytest.mark.anyio
async def test_sync_payment_status_creates_missing_failed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(id=uuid4(), order_id=uuid4(), payment_status_id=None),
    )
    created_status = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=None),
    )
    create_mock = AsyncMock(return_value=created_status)
    monkeypatch.setattr(crud_payment_status, "create_draft", create_mock)

    await _sync_payment_status_for_provider_status(
        session=session, payment=payment, trans_status="REFUSED"
    )

    assert payment.payment_status_id == created_status.id
    create_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_sync_payment_status_ignores_unknown_status() -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            payment_status_id=None,
        ),
    )

    await _sync_payment_status_for_provider_status(
        session=session, payment=payment, trans_status="UNDER_REVIEW"
    )

    assert payment.payment_status_id is None


@pytest.mark.anyio
async def test_publish_provider_outcome_event_publishes_captured_on_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            user_id=uuid4(),
            provider_code="payzen",
            provider_reference="tx-123",
            provider_data={"trans_id": "tx-123", "trans_status": "PAID"},
        ),
    )

    publish_mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.payments.outbox_registry.publish", publish_mock)

    await _publish_provider_outcome_event(
        session=session, payment=payment, trans_status="PAID"
    )

    publish_mock.assert_awaited_once()
    kwargs = publish_mock.call_args.kwargs
    assert kwargs["event_type"] == "payment.captured"
    assert kwargs["payload"]["payment_id"] == str(payment.id)
    assert kwargs["payload"]["order_id"] == str(payment.order_id)
    assert kwargs["payload"]["provider_code"] == "payzen"
    assert kwargs["payload"]["metadata"]["trans_status"] == "PAID"


@pytest.mark.anyio
async def test_publish_provider_outcome_event_publishes_rejected_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            user_id=uuid4(),
            provider_code="payzen",
            provider_reference=None,
            provider_data=None,
        ),
    )
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.payments.outbox_registry.publish", publish_mock)

    await _publish_provider_outcome_event(
        session=session, payment=payment, trans_status="REFUSED"
    )

    publish_mock.assert_awaited_once()
    assert publish_mock.call_args.kwargs["event_type"] == "payment.rejected"


@pytest.mark.anyio
async def test_publish_provider_outcome_event_skips_non_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            user_id=uuid4(),
            provider_code="payzen",
            provider_reference=None,
            provider_data=None,
        ),
    )
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.payments.outbox_registry.publish", publish_mock)

    await _publish_provider_outcome_event(
        session=session, payment=payment, trans_status="UNDER_REVIEW"
    )

    publish_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_publish_provider_webhook_received_event_publishes_audit_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            user_id=uuid4(),
            provider_code="payzen",
            provider_reference="order-123",
        ),
    )

    publish_mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.payments.outbox_registry.publish", publish_mock)

    await _publish_provider_webhook_received_event(
        session=session,
        payment=payment,
        raw_payload={"kr-answer": "raw", "count": 1},
        validated_payload={"order_id": "order-123", "trans_status": "PAID"},
        trans_status="PAID",
        trans_id="tx-999",
    )

    publish_mock.assert_awaited_once()
    kwargs = publish_mock.call_args.kwargs
    assert kwargs["event_type"] == "payment.webhook_received"
    assert kwargs["payload"]["payment_id"] == str(payment.id)
    assert kwargs["payload"]["metadata"]["raw_payload"]["kr-answer"] == "raw"
    assert kwargs["payload"]["metadata"]["trans_id"] == "tx-999"


@pytest.mark.anyio
async def test_payzen_ipn_updates_payment_inline_and_publishes_outbox_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            user_id=uuid4(),
            provider_code="payzen",
            provider_reference="tx-1",
            payment_status_id=None,
            provider_data={"trans_id": "tx-1"},
            amount=Decimal("1500"),
            currency="XPF",
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "PAID",
                "amount": "1500",
                "payment_cards": "VISA",
                "_raw_answer": {},
            }
        ),
    )
    monkeypatch.setattr(
        crud_payment,
        "get_by_provider_reference",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        crud_payment,
        "update_payment_from_webhook_payload",
        AsyncMock(return_value=payment),
    )

    sync_payment_status_mock = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.payments._sync_payment_status_for_provider_status",
        sync_payment_status_mock,
    )
    publish_event_mock = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_outcome_event",
        publish_event_mock,
    )
    publish_webhook_received_mock = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_webhook_received_event",
        publish_webhook_received_mock,
    )

    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "ignored"})),
    )
    response = await payzen_ipn(session=session, request=request)

    assert response.status_code == 200

    sync_payment_status_mock.assert_awaited_once()
    publish_webhook_received_mock.assert_awaited_once()
    publish_event_mock.assert_awaited_once()
    # publish_event_mock must run BEFORE commit (event is part of the
    # same transaction as the Payment update — outbox guarantee)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
