import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Request

from app.api.routes.payments import payzen_ipn
from app.features.payment.crud.payment import crud_payment
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



@pytest.mark.anyio
async def test_payzen_ipn_ignores_duplicate_terminal_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            provider_code="payzen",
            provider_reference=None,
            provider_data={"trans_status": "PAID", "trans_id": "tx-001"},
            payment_status_id=None,
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "PAID",
                "trans_uuid": "tx-001",
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

    update_payment_mock = AsyncMock(return_value=payment)
    monkeypatch.setattr(
        crud_payment,
        "update_payment_from_webhook_payload",
        update_payment_mock,
    )

    sync_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.routes.payments._sync_payment_status_for_provider_status",
        sync_mock,
    )
    publish_event_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_outcome_event",
        publish_event_mock,
    )
    publish_webhook_received_mock = AsyncMock(return_value=None)
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
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["message"] == "IPN deja traite"

    update_payment_mock.assert_not_awaited()
    sync_mock.assert_not_awaited()
    publish_webhook_received_mock.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_payzen_ipn_ignores_conflicting_terminal_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            provider_code="payzen",
            provider_reference=None,
            provider_data={"trans_status": "PAID", "trans_id": "tx-paid"},
            payment_status_id=None,
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "REFUSED",
                "trans_uuid": "tx-refused",
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

    update_payment_mock = AsyncMock(return_value=payment)
    monkeypatch.setattr(
        crud_payment,
        "update_payment_from_webhook_payload",
        update_payment_mock,
    )

    sync_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.routes.payments._sync_payment_status_for_provider_status",
        sync_mock,
    )
    publish_event_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_outcome_event",
        publish_event_mock,
    )
    publish_webhook_received_mock = AsyncMock(return_value=None)
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
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["message"] == "IPN terminal contradictoire ignore"

    update_payment_mock.assert_not_awaited()
    sync_mock.assert_not_awaited()
    publish_webhook_received_mock.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
