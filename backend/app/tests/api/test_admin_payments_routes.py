from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.admin_payments import (
    PaymentApproveRequest,
    PaymentRejectRequest,
    approve_payment,
    list_pending_validation,
    reject_payment,
)
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
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
            provider_reference="ref-init",
            provider_data=None,
            payment_status_id=None,
        ),
    )


def _make_admin() -> Any:
    return SimpleNamespace(id=uuid4(), is_superuser=True)


def _make_status(name: str) -> PaymentStatus:
    return cast(PaymentStatus, SimpleNamespace(id=uuid4(), name=name))


def _make_validation_namespace(action: str, payment_id: Any) -> PaymentValidation:
    return cast(
        PaymentValidation,
        SimpleNamespace(
            id=uuid4(),
            payment_id=payment_id,
            action=action,
            admin_user_id=uuid4(),
            reason=None,
            extra_data=None,
            is_active=True,
            created_at=None,
            created_by_id=None,
            modify_at=None,
            modify_by_id=None,
        ),
    )


@pytest.mark.anyio
async def test_list_pending_validation_returns_empty_when_no_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    monkeypatch.setattr(
        crud_payment_status, "get_by_name", AsyncMock(return_value=None)
    )

    result = await list_pending_validation(
        session=session, _admin=cast(Any, _make_admin())
    )

    assert result == []


@pytest.mark.anyio
async def test_list_pending_validation_returns_manual_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    awaiting_status = _make_status(MANUAL_STATUS_AWAITING_VALIDATION)
    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=awaiting_status),
    )

    payments = [_make_payment(), _make_payment(provider_code="manual_transfer")]
    session = AsyncMock()

    def _result(rows: list[Any]) -> Mock:
        result = Mock()
        result.all.return_value = rows
        return result

    # Three queries: the payments, their users, then their order numbers.
    session.exec = AsyncMock(
        side_effect=[
            _result(payments),
            _result([]),
            _result([(payments[0].order_id, "CMD-2026-00042")]),
        ]
    )

    result = await list_pending_validation(
        session=session, _admin=cast(Any, _make_admin())
    )

    assert len(result) == 2
    assert result[0].provider_code == "manual_check"
    assert result[1].provider_code == "manual_transfer"
    assert result[0].order_number == "CMD-2026-00042"
    assert result[1].order_number is None


@pytest.mark.anyio
async def test_approve_payment_persists_validation_and_publishes_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    payment = _make_payment()
    admin = _make_admin()

    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    completed_status = _make_status(MANUAL_STATUS_COMPLETED)
    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=completed_status),
    )

    validation = _make_validation_namespace("approve", payment.id)
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.crud_payment_validation.create_draft",
        AsyncMock(return_value=validation),
    )
    publish_mock = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.outbox_registry.publish",
        publish_mock,
    )

    response = await approve_payment(
        payment_id=payment.id,
        body=PaymentApproveRequest(reference="CHK-7", comment="ok"),
        session=session,
        admin=cast(Any, admin),
    )

    assert response.payment_id == payment.id
    assert response.payment_status_id == completed_status.id
    assert response.validation.action == "approve"

    publish_mock.assert_awaited_once()
    kwargs = publish_mock.call_args.kwargs
    assert kwargs["event_type"] == mp.EVENT_CAPTURED

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_approve_payment_rejects_non_manual_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = _make_payment(provider_code="payzen")
    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    with pytest.raises(AppError) as exc_info:
        await approve_payment(
            payment_id=payment.id,
            body=PaymentApproveRequest(),
            session=session,
            admin=cast(Any, _make_admin()),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "payment.not_manual"
    session.rollback.assert_awaited_once()


@pytest.mark.anyio
async def test_approve_payment_returns_404_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    monkeypatch.setattr(
        crud_payment,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("missing")),
    )

    with pytest.raises(AppError) as exc_info:
        await approve_payment(
            payment_id=uuid4(),
            body=PaymentApproveRequest(),
            session=session,
            admin=cast(Any, _make_admin()),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "payment.not_found"


@pytest.mark.anyio
async def test_reject_payment_persists_validation_and_publishes_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    payment = _make_payment()
    admin = _make_admin()

    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    failed_status = _make_status(MANUAL_STATUS_FAILED)
    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=failed_status),
    )

    validation = _make_validation_namespace("reject", payment.id)
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.crud_payment_validation.create_draft",
        AsyncMock(return_value=validation),
    )
    publish_mock = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.manual_payment.outbox_registry.publish",
        publish_mock,
    )

    response = await reject_payment(
        payment_id=payment.id,
        body=PaymentRejectRequest(reason="No funds"),
        session=session,
        admin=cast(Any, admin),
    )

    assert response.payment_id == payment.id
    assert response.payment_status_id == failed_status.id
    assert response.validation.action == "reject"

    publish_mock.assert_awaited_once()
    kwargs = publish_mock.call_args.kwargs
    assert kwargs["event_type"] == mp.EVENT_REJECTED
    assert kwargs["payload"]["reason"] == "No funds"
