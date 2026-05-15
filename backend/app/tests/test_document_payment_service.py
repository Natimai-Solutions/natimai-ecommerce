from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_attachment import PaymentAttachment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.payment_validation import PaymentValidation
from app.features.payment.providers.document_validated import (
    DOCUMENT_STATUS_APPROVED,
    DOCUMENT_STATUS_DOCUMENT_REQUIRED,
    DOCUMENT_STATUS_DOCUMENT_UPLOADED,
    DOCUMENT_STATUS_REJECTED,
)
from app.features.payment.services import document_payment as dp


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_payment(provider_code: str = "po_public") -> Payment:
    return cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            order_id=uuid4(),
            amount=Decimal("500.00"),
            currency="EUR",
            provider_code=provider_code,
            provider_reference=None,
            provider_data=None,
            payment_status_id=None,
            payzen_status=None,
        ),
    )


def _make_status(name: str) -> PaymentStatus:
    return cast(PaymentStatus, SimpleNamespace(id=uuid4(), name=name))


def _make_attachment() -> PaymentAttachment:
    return cast(
        PaymentAttachment,
        SimpleNamespace(
            id=uuid4(),
            file_key="payments/abc/po.pdf",
            filename="po.pdf",
            mimetype="application/pdf",
        ),
    )


def _patch_validation_factory(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    validation = cast(PaymentValidation, SimpleNamespace(id=uuid4()))
    mock = AsyncMock(return_value=validation)
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.crud_payment_validation.create_draft",
        mock,
    )
    return mock


@pytest.mark.anyio
async def test_register_intent_publishes_document_required_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    status = _make_status(DOCUMENT_STATUS_DOCUMENT_REQUIRED)
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.crud_payment_status.get_by_name",
        AsyncMock(return_value=status),
    )
    _patch_validation_factory(monkeypatch)

    publish = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.outbox_registry.publish",
        publish,
    )

    payment = _make_payment()
    result = await dp.register_intent(
        session,
        payment=payment,
        instructions="please upload PO",
        user=None,
    )

    assert result.payment_status_id == status.id
    publish.assert_awaited_once()
    kwargs = publish.call_args.kwargs
    assert kwargs["event_type"] == dp.EVENT_DOCUMENT_REQUIRED


@pytest.mark.anyio
async def test_mark_document_uploaded_publishes_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    status = _make_status(DOCUMENT_STATUS_DOCUMENT_UPLOADED)
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.crud_payment_status.get_by_name",
        AsyncMock(return_value=status),
    )
    _patch_validation_factory(monkeypatch)

    publish = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.outbox_registry.publish",
        publish,
    )

    payment = _make_payment()
    attachment = _make_attachment()

    result = await dp.mark_document_uploaded(
        session, payment=payment, attachment=attachment, user=None
    )

    assert result.payment_status_id == status.id
    publish.assert_awaited_once()
    kwargs = publish.call_args.kwargs
    assert kwargs["event_type"] == dp.EVENT_DOCUMENT_UPLOADED
    assert kwargs["payload"]["attachment_id"] == str(attachment.id)
    assert kwargs["payload"]["metadata"]["file_key"] == attachment.file_key


@pytest.mark.anyio
async def test_mark_document_uploaded_rejects_non_document_provider() -> None:
    session = AsyncMock()
    payment = _make_payment(provider_code="payzen")
    attachment = _make_attachment()

    with pytest.raises(dp.PaymentNotDocumentValidatedError):
        await dp.mark_document_uploaded(
            session, payment=payment, attachment=attachment, user=None
        )


@pytest.mark.anyio
async def test_approve_document_payment_publishes_captured_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    status = _make_status(DOCUMENT_STATUS_APPROVED)
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.crud_payment_status.get_by_name",
        AsyncMock(return_value=status),
    )
    _patch_validation_factory(monkeypatch)

    publish = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.outbox_registry.publish",
        publish,
    )

    payment = _make_payment()
    admin = cast(Any, SimpleNamespace(id=uuid4()))

    outcome = await dp.approve_document_payment(
        session, payment=payment, admin=admin, comment="ok"
    )

    assert outcome.payment.payment_status_id == status.id
    kwargs = publish.call_args.kwargs
    assert kwargs["event_type"] == dp.EVENT_DOCUMENT_APPROVED


@pytest.mark.anyio
async def test_reject_document_payment_publishes_rejected_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    status = _make_status(DOCUMENT_STATUS_REJECTED)
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.crud_payment_status.get_by_name",
        AsyncMock(return_value=status),
    )
    _patch_validation_factory(monkeypatch)

    publish = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.outbox_registry.publish",
        publish,
    )

    payment = _make_payment()
    admin = cast(Any, SimpleNamespace(id=uuid4()))

    outcome = await dp.reject_document_payment(
        session, payment=payment, admin=admin, reason="missing signature"
    )

    assert outcome.payment.payment_status_id == status.id
    kwargs = publish.call_args.kwargs
    assert kwargs["event_type"] == dp.EVENT_DOCUMENT_REJECTED
    assert kwargs["payload"]["reason"] == "missing signature"


@pytest.mark.anyio
async def test_mark_document_infected_publishes_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    status = _make_status(DOCUMENT_STATUS_REJECTED)
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.crud_payment_status.get_by_name",
        AsyncMock(return_value=status),
    )
    _patch_validation_factory(monkeypatch)

    publish = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.outbox_registry.publish",
        publish,
    )

    payment = _make_payment()
    attachment = _make_attachment()

    result = await dp.mark_document_infected(
        session,
        payment=payment,
        attachment=attachment,
        signature="EICAR-Test-File",
    )

    assert result.payment_status_id == status.id
    kwargs = publish.call_args.kwargs
    assert kwargs["event_type"] == dp.EVENT_DOCUMENT_INFECTED
    assert kwargs["payload"]["metadata"] == {"signature": "EICAR-Test-File"}
