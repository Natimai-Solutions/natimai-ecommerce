from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.payments import PaymentsInitiateRequest, initiate_payment
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import Payment
from app.features.payment.providers.base import InitiationRequest, InitiationResult
from app.features.payment.services.provider_dispatch import (
    PaymentMethodNotFoundError,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_payments_initiate_dispatches_by_payment_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            payment_method_id=None,
            provider_code=None,
            provider_reference=None,
            provider_data=None,
            payzen_form_token=None,
            payzen_order_id=None,
        ),
    )

    monkeypatch.setattr(
        crud_payment,
        "create_payment_with_log",
        AsyncMock(return_value=payment),
    )

    captured_provider_code: str | None = None
    captured_request: InitiationRequest | None = None

    async def _fake_resolve_provider_code(
        session_arg: object,
        payment_method_id: object,
    ) -> str:
        assert session_arg is session
        assert payment_method_id == request.payment_method_id
        return "payzen"

    async def _fake_initiate_api_payment(
        provider_code: str,
        request_payload: InitiationRequest,
    ) -> InitiationResult:
        nonlocal captured_provider_code, captured_request
        captured_provider_code = provider_code
        captured_request = request_payload
        return InitiationResult(
            provider_code="payzen",
            provider_reference="tx_123",
            form_token="token_123",
            server_url="https://static.osb.pf",
            public_key="pk_test",
            raw_response={"status": "SUCCESS"},
        )

    monkeypatch.setattr(
        "app.api.routes.payments.resolve_provider_code_for_payment_method",
        _fake_resolve_provider_code,
    )
    monkeypatch.setattr(
        "app.api.routes.payments.initiate_api_payment",
        _fake_initiate_api_payment,
    )

    request = PaymentsInitiateRequest(
        payment_method_id=uuid4(),
        amount=Decimal("12.34"),
        currency="EUR",
        order_id=None,
        return_url="https://example.com/return",
        metadata={"source": "test"},
    )
    current_user = cast(
        Any,
        SimpleNamespace(
            id=uuid4(),
            email="client@example.com",
            full_name="Jane Doe",
        ),
    )

    response = await initiate_payment(
        session=session,
        request=request,
        current_user=current_user,
    )

    assert captured_provider_code == "payzen"
    assert captured_request is not None
    assert captured_request.amount == 1234
    assert captured_request.currency == "EUR"
    assert captured_request.order_id == str(payment.id)

    assert payment.payment_method_id == request.payment_method_id
    assert payment.provider_code == "payzen"
    assert payment.provider_reference == "tx_123"
    assert payment.provider_data == {"status": "SUCCESS"}
    assert payment.payzen_form_token == "token_123"
    assert payment.payzen_order_id == str(payment.id)

    assert response.payment_id == payment.id
    assert response.provider_code == "payzen"
    assert response.form_token == "token_123"

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_payments_initiate_returns_404_when_method_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()

    create_payment_mock = AsyncMock()
    monkeypatch.setattr(crud_payment, "create_payment_with_log", create_payment_mock)
    monkeypatch.setattr(
        "app.api.routes.payments.resolve_provider_code_for_payment_method",
        AsyncMock(side_effect=PaymentMethodNotFoundError("payment method not found")),
    )

    request = PaymentsInitiateRequest(
        payment_method_id=uuid4(),
        amount=Decimal("10.00"),
        currency="EUR",
        order_id=None,
    )
    current_user = cast(
        Any,
        SimpleNamespace(
            id=uuid4(),
            email="client@example.com",
            full_name="",
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await initiate_payment(
            session=session,
            request=request,
            current_user=current_user,
        )

    assert exc_info.value.status_code == 404
    create_payment_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_payments_initiate_returns_400_when_provider_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            payment_method_id=None,
            provider_code=None,
            provider_reference=None,
            provider_data=None,
            payzen_form_token=None,
            payzen_order_id=None,
        ),
    )

    monkeypatch.setattr(
        crud_payment,
        "create_payment_with_log",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        "app.api.routes.payments.resolve_provider_code_for_payment_method",
        AsyncMock(return_value="future_provider"),
    )
    monkeypatch.setattr(
        "app.api.routes.payments.get_provider",
        lambda provider_code: object(),
    )

    request = PaymentsInitiateRequest(
        payment_method_id=uuid4(),
        amount=Decimal("10.00"),
        currency="EUR",
        order_id=None,
    )
    current_user = cast(
        Any,
        SimpleNamespace(
            id=uuid4(),
            email="client@example.com",
            full_name="",
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await initiate_payment(
            session=session,
            request=request,
            current_user=current_user,
        )

    assert exc_info.value.status_code == 400
    assert "does not support payment initiation" in str(exc_info.value.detail)
    session.rollback.assert_awaited_once()
