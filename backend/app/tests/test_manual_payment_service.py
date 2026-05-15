from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.payment_validation import PaymentValidation
from app.features.payment.providers.manual import (
    MANUAL_STATUS_AWAITING_VALIDATION,
    MANUAL_STATUS_COMPLETED,
    MANUAL_STATUS_FAILED,
)
from app.features.payment.services import manual_payment as mp


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_payment(provider_code: str = "manual_check") -> Payment:
    return cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            order_id=uuid4(),
            amount=Decimal("100.00"),
            currency="XPF",
            provider_code=provider_code,
            provider_reference=None,
            provider_data=None,
            payment_status_id=None,
            payzen_status=None,
        ),
    )


def _make_status(name: str) -> PaymentStatus:
    return cast(
        PaymentStatus,
        SimpleNamespace(id=uuid4(), name=name),
    )


@pytest.mark.anyio
async def test_register_intent_publishes_outbox_and_sets_awaiting_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    awaiting_status = _make_status(MANUAL_STATUS_AWAITING_VALIDATION)
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.crud_payment_status.get_by_name",
        AsyncMock(return_value=awaiting_status),
    )

    validation = cast(PaymentValidation, SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.crud_payment_validation.create_draft",
        AsyncMock(return_value=validation),
    )

    publish_mock = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.outbox_registry.publish",
        publish_mock,
    )

    payment = _make_payment()

    result = await mp.register_intent(
        session,
        payment=payment,
        instructions="Send your check to ...",
        user=None,
    )

    assert result is payment
    assert payment.payment_status_id == awaiting_status.id
    publish_mock.assert_awaited_once()
    args, kwargs = publish_mock.call_args
    assert kwargs["event_type"] == mp.EVENT_AWAITING_VALIDATION
    assert kwargs["payload"]["payment_id"] == str(payment.id)
    assert kwargs["payload"]["order_id"] == str(payment.order_id)
    assert kwargs["payload"]["provider_code"] == "manual_check"


@pytest.mark.anyio
async def test_approve_manual_payment_publishes_captured_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    completed_status = _make_status(MANUAL_STATUS_COMPLETED)
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.crud_payment_status.get_by_name",
        AsyncMock(return_value=completed_status),
    )

    validation = cast(PaymentValidation, SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.crud_payment_validation.create_draft",
        AsyncMock(return_value=validation),
    )

    publish_mock = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.outbox_registry.publish",
        publish_mock,
    )

    payment = _make_payment()
    admin = cast(Any, SimpleNamespace(id=uuid4()))

    outcome = await mp.approve_manual_payment(
        session,
        payment=payment,
        admin=admin,
        reference="CHK-101",
        comment="received in mail",
    )

    assert outcome.payment.payment_status_id == completed_status.id
    assert outcome.payment.provider_reference == "CHK-101"

    publish_mock.assert_awaited_once()
    kwargs = publish_mock.call_args.kwargs
    assert kwargs["event_type"] == mp.EVENT_CAPTURED
    assert kwargs["payload"]["action"] == mp.ACTION_APPROVE
    assert kwargs["payload"]["admin_user_id"] == str(admin.id)
    assert kwargs["payload"]["reference"] == "CHK-101"
    assert kwargs["payload"]["reason"] == "received in mail"


@pytest.mark.anyio
async def test_reject_manual_payment_publishes_rejected_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    failed_status = _make_status(MANUAL_STATUS_FAILED)
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.crud_payment_status.get_by_name",
        AsyncMock(return_value=failed_status),
    )

    validation = cast(PaymentValidation, SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.crud_payment_validation.create_draft",
        AsyncMock(return_value=validation),
    )

    publish_mock = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.outbox_registry.publish",
        publish_mock,
    )

    payment = _make_payment()
    admin = cast(Any, SimpleNamespace(id=uuid4()))

    outcome = await mp.reject_manual_payment(
        session,
        payment=payment,
        admin=admin,
        reason="Funds never received",
    )

    assert outcome.payment.payment_status_id == failed_status.id

    publish_mock.assert_awaited_once()
    kwargs = publish_mock.call_args.kwargs
    assert kwargs["event_type"] == mp.EVENT_REJECTED
    assert kwargs["payload"]["reason"] == "Funds never received"


@pytest.mark.anyio
async def test_approve_manual_payment_rejects_non_manual_provider() -> None:
    session = AsyncMock()

    payment = _make_payment(provider_code="payzen")
    admin = cast(Any, SimpleNamespace(id=uuid4()))

    with pytest.raises(mp.PaymentNotManualError):
        await mp.approve_manual_payment(
            session,
            payment=payment,
            admin=admin,
            reference=None,
            comment=None,
        )


@pytest.mark.anyio
async def test_reject_manual_payment_rejects_non_manual_provider() -> None:
    session = AsyncMock()

    payment = _make_payment(provider_code="payzen")
    admin = cast(Any, SimpleNamespace(id=uuid4()))

    with pytest.raises(mp.PaymentNotManualError):
        await mp.reject_manual_payment(
            session,
            payment=payment,
            admin=admin,
            reason="ignored",
        )
