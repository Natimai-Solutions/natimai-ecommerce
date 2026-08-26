from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.payments import PaymentsInitiateRequest, initiate_payment
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import Payment


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_payments_initiate_dispatches_manual_check(
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
            payment_status_id=None,
            order_id=uuid4(),
            user_id=uuid4(),
        ),
    )

    monkeypatch.setattr(
        crud_payment,
        "create_payment_with_log",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.resolve_provider_code_for_payment_method",
        AsyncMock(return_value="manual_check"),
    )

    captured: dict[str, Any] = {}

    async def _fake_register_intent(
        session_arg: object,
        *,
        payment: Payment,
        instructions: str | None,
        user: object | None,
    ) -> Payment:
        captured["session"] = session_arg
        captured["payment"] = payment
        captured["instructions"] = instructions
        captured["user"] = user
        return payment

    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.register_manual_intent",
        _fake_register_intent,
    )
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.check_payment_method_eligible",
        AsyncMock(return_value=True),
    )
    # Order revalidation is covered by test_payments_initiate_order_guard.py;
    # this test focuses on the manual-provider dispatch.
    monkeypatch.setattr(
        "app.api.routes.payments._validate_order_for_initiation",
        AsyncMock(return_value=None),
    )

    request = PaymentsInitiateRequest(
        payment_method_id=uuid4(),
        amount=Decimal("250.00"),
        currency="XPF",
        order_id=payment.order_id,
    )
    current_user = cast(
        Any,
        SimpleNamespace(
            id=payment.user_id,
            email="client@example.com",
            full_name="Jane Doe",
            price_group_id=None,
        ),
    )

    response = await initiate_payment(
        session=session,
        request=request,
        current_user=current_user,
    )

    assert response.provider_code == "manual_check"
    assert response.instructions is not None
    assert "chèque" in response.instructions.lower()
    assert response.form_token is None
    assert response.redirect_url is None
    assert captured["payment"] is payment
    assert captured["user"] is current_user
    assert payment.provider_code == "manual_check"
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_payments_initiate_dispatches_manual_transfer(
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
            payment_status_id=None,
            order_id=None,
            user_id=uuid4(),
        ),
    )

    monkeypatch.setattr(
        crud_payment,
        "create_payment_with_log",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.resolve_provider_code_for_payment_method",
        AsyncMock(return_value="manual_transfer"),
    )
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.register_manual_intent",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.check_payment_method_eligible",
        AsyncMock(return_value=True),
    )

    request = PaymentsInitiateRequest(
        payment_method_id=uuid4(),
        amount=Decimal("99.00"),
        currency="EUR",
    )
    current_user = cast(
        Any,
        SimpleNamespace(
            id=payment.user_id,
            email="c@example.com",
            full_name="",
            price_group_id=None,
        ),
    )

    response = await initiate_payment(
        session=session,
        request=request,
        current_user=current_user,
    )

    assert response.provider_code == "manual_transfer"
    assert response.instructions is not None
    assert "virement" in response.instructions.lower()
