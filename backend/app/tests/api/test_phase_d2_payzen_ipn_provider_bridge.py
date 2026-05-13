from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Request

from app.api.routes.payments import payzen_ipn, validate_ipn_signature
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import Payment
from app.features.payment.providers.base import WebhookResult


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_validate_ipn_signature_delegates_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_provider_code: str | None = None
    captured_payload: dict[str, Any] | None = None
    expected_payload: dict[str, Any] = {
        "order_id": "order_123",
        "trans_status": "PAID",
        "trans_uuid": "tx_123",
    }

    def _fake_parse_api_webhook(
        provider_code: str,
        payload: dict[str, Any],
    ) -> WebhookResult:
        nonlocal captured_provider_code, captured_payload
        captured_provider_code = provider_code
        captured_payload = payload
        return WebhookResult(
            provider_code="payzen",
            provider_reference="tx_123",
            payment_status="PAID",
            payload=expected_payload,
        )

    monkeypatch.setattr(
        "app.api.routes.payments.parse_api_webhook",
        _fake_parse_api_webhook,
    )

    parsed = validate_ipn_signature({"kr-answer": "raw"})

    assert parsed == expected_payload
    assert captured_provider_code == "payzen"
    assert captured_payload == {"kr-answer": "raw"}


@pytest.mark.anyio
async def test_payzen_ipn_uses_provider_parser_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    captured_provider_code: str | None = None
    captured_payload: dict[str, Any] | None = None

    payment = cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            payzen_status=None,
            payzen_trans_id=None,
            payment_status_id=None,
        ),
    )

    parsed_fields: dict[str, Any] = {
        "order_id": str(payment.id),
        "trans_status": "PAID",
        "trans_uuid": "tx_001",
        "amount": "1500",
        "payment_cards": "VISA",
        "_raw_answer": {},
    }

    def _fake_parse_api_webhook(
        provider_code: str,
        payload: dict[str, Any],
    ) -> WebhookResult:
        nonlocal captured_provider_code, captured_payload
        captured_provider_code = provider_code
        captured_payload = payload
        return WebhookResult(
            provider_code="payzen",
            provider_reference="tx_001",
            payment_status="PAID",
            payload=parsed_fields,
        )

    monkeypatch.setattr(
        "app.api.routes.payments.parse_api_webhook",
        _fake_parse_api_webhook,
    )
    monkeypatch.setattr(
        crud_payment,
        "get_by_payzen_order_id",
        AsyncMock(return_value=payment),
    )

    update_payment_mock = AsyncMock(return_value=payment)
    monkeypatch.setattr(
        crud_payment,
        "update_payment_from_payzen",
        update_payment_mock,
    )

    sync_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.routes.payments._sync_checkout_entities_for_payzen_status",
        sync_mock,
    )

    request = cast(
        Request,
        SimpleNamespace(
            form=AsyncMock(return_value={"kr-answer": "raw", "kr-hash": "abc"})
        ),
    )
    response = await payzen_ipn(session=session, request=request)

    assert response.status_code == 200
    assert captured_provider_code == "payzen"
    assert captured_payload == {"kr-answer": "raw", "kr-hash": "abc"}

    update_payment_mock.assert_awaited_once()
    sync_mock.assert_awaited_once()
    session.commit.assert_awaited_once()
