from typing import Any

import pytest

from app.features.payment.providers import SUPPORTED_PROVIDERS, get_provider
from app.features.payment.providers.base import (
    InitiationRequest,
    UnknownPaymentProviderError,
)
from app.features.payment.providers.payzen import PayzenProvider


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_supported_providers_contains_payzen() -> None:
    assert "payzen" in SUPPORTED_PROVIDERS
    assert SUPPORTED_PROVIDERS["payzen"] is PayzenProvider


def test_get_provider_returns_payzen_instance() -> None:
    provider = get_provider("payzen")

    assert isinstance(provider, PayzenProvider)


def test_get_provider_normalizes_provider_code() -> None:
    provider = get_provider("  PayZen  ")

    assert isinstance(provider, PayzenProvider)


def test_get_provider_unknown_provider_raises() -> None:
    with pytest.raises(UnknownPaymentProviderError):
        get_provider("unknown")


@pytest.mark.anyio
async def test_payzen_provider_initiate_payment_delegates_to_utility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_args: dict[str, Any] = {}

    async def _fake_create_payzen_form_token(**kwargs: Any) -> dict[str, Any]:
        captured_args.update(kwargs)
        return {
            "form_token": "token_123",
            "server_url": "https://static.osb.pf",
            "public_key": "pk_123",
            "raw_response": {"status": "SUCCESS"},
        }

    monkeypatch.setattr(
        "app.features.payment.providers.payzen.create_payzen_form_token",
        _fake_create_payzen_form_token,
    )

    provider = PayzenProvider()
    result = await provider.initiate_payment(
        InitiationRequest(
            amount=1200,
            currency="XPF",
            order_id="order_123",
            customer_email="test@example.com",
            customer_reference="customer_1",
            metadata={"source": "test"},
        )
    )

    assert captured_args["order_id"] == "order_123"
    assert captured_args["amount"] == 1200
    assert result.provider_code == "payzen"
    assert result.form_token == "token_123"
    assert result.server_url == "https://static.osb.pf"
    assert result.public_key == "pk_123"
    assert result.raw_response == {"status": "SUCCESS"}


def test_payzen_provider_parse_webhook_delegates_to_utility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_fields: dict[str, Any] = {
        "trans_uuid": "tr_123",
        "trans_status": "PAID",
        "order_id": "order_123",
    }

    monkeypatch.setattr(
        "app.features.payment.providers.payzen.validate_ipn_signature",
        lambda payload: expected_fields,
    )

    provider = PayzenProvider()
    result = provider.parse_webhook_notification({"kr-answer": "raw"})

    assert result.provider_code == "payzen"
    assert result.provider_reference == "order_123"
    assert result.payment_status == "PAID"
    assert result.payload == expected_fields
