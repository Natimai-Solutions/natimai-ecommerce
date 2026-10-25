"""IPN amount guard (S1 audit fix, defence in depth).

A success IPN (PAID / AUTHORISED) whose amount differs from the amount the
payment was created with must never complete the payment nor publish the
``payment.captured`` event — it is recorded on the payment for manual review
and acknowledged with an error message so PayZen stops retrying.
"""

import json
from decimal import Decimal
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
async def test_payzen_ipn_rejects_paid_amount_mismatch(
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
            provider_data=None,
            payment_status_id=None,
            amount=Decimal("25000"),
            currency="XPF",
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "PAID",
                "trans_uuid": "tx-1",
                "amount": "1",
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
    assert payload["status"] == "error"
    assert "Montant IPN inattendu" in payload["message"]

    # The payment is never completed and no outcome event is published.
    update_payment_mock.assert_not_awaited()
    sync_mock.assert_not_awaited()
    publish_event_mock.assert_not_awaited()
    # The audit trail is preserved: webhook event + anomaly on the payment.
    publish_webhook_received_mock.assert_awaited_once()
    assert payment.provider_data is not None
    mismatch = payment.provider_data["amount_mismatch"]
    assert mismatch["expected"] == "25000"
    assert mismatch["received"] == "1"
    assert mismatch["trans_status"] == "PAID"
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_payzen_ipn_rejects_authorised_amount_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deferred-capture flow: an AUTHORISED IPN is guarded the same way."""
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            provider_code="payzen",
            provider_reference=None,
            provider_data=None,
            payment_status_id=None,
            amount=Decimal("25000"),
            currency="XPF",
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "AUTHORISED",
                "trans_uuid": "tx-2",
                "amount": "24000",
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
    monkeypatch.setattr(
        "app.api.routes.payments._sync_payment_status_for_provider_status",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_outcome_event",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_webhook_received_event",
        AsyncMock(return_value=None),
    )

    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "ignored"})),
    )
    response = await payzen_ipn(session=session, request=request)

    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["status"] == "error"
    update_payment_mock.assert_not_awaited()
    assert payment.provider_data is not None
    assert payment.provider_data["amount_mismatch"]["received"] == "24000"


@pytest.mark.anyio
async def test_payzen_ipn_treats_unreadable_amount_as_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-integer amount must not answer 500.

    ``parse_minor_units`` raises on such a value; letting it bubble up returned
    a 500 for a deterministic error, so PayZen replayed the same IPN forever.
    It is now recorded like any other mismatch and acknowledged.
    """
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            provider_code="payzen",
            provider_reference=None,
            provider_data=None,
            payment_status_id=None,
            amount=Decimal("25000"),
            currency="XPF",
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment.id),
                "trans_status": "PAID",
                "trans_uuid": "tx-1",
                "amount": "250,00",  # comma decimal — not minor units
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
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_webhook_received_event",
        AsyncMock(return_value=None),
    )

    request = cast(
        Request,
        SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "ignored"})),
    )
    response = await payzen_ipn(session=session, request=request)

    assert response.status_code == 200
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["status"] == "error"

    update_payment_mock.assert_not_awaited()
    sync_mock.assert_not_awaited()
    publish_event_mock.assert_not_awaited()
    assert payment.provider_data is not None
    mismatch = payment.provider_data["amount_mismatch"]
    assert mismatch["unreadable"] is True
    assert mismatch["received"] == "250,00"
    session.rollback.assert_not_awaited()
