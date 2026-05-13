from typing import Any

import pytest

from app.features.payment.providers.base import (
    ApiPaymentProvider,
    InitiationRequest,
    InitiationResult,
    WebhookResult,
)
from app.features.payment.providers.payzen import PayzenProvider
from app.features.payment.services.provider_dispatch import (
    PaymentApiProviderResolutionError,
    initiate_api_payment,
    parse_api_webhook,
    resolve_api_provider,
)


class _FakeApiProvider(ApiPaymentProvider):
    code = "fake"

    def __init__(self) -> None:
        self.last_initiation_request: InitiationRequest | None = None
        self.last_payload: dict[str, Any] | None = None

    async def initiate_payment(self, request: InitiationRequest) -> InitiationResult:
        self.last_initiation_request = request
        return InitiationResult(
            provider_code=self.code,
            provider_reference="fake_ref",
            form_token="fake_token",
            server_url="https://fake.server",
            public_key="fake_key",
        )

    def parse_webhook_notification(self, payload: dict[str, Any]) -> WebhookResult:
        self.last_payload = payload
        return WebhookResult(
            provider_code=self.code,
            provider_reference="fake_ref",
            payment_status="PAID",
            payload={"parsed": True},
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_resolve_api_provider_returns_payzen_provider() -> None:
    provider = resolve_api_provider("payzen")

    assert isinstance(provider, PayzenProvider)


def test_resolve_api_provider_rejects_non_api_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.features.payment.services.provider_dispatch.get_provider",
        lambda provider_code: object(),
    )

    with pytest.raises(PaymentApiProviderResolutionError):
        resolve_api_provider("payzen")


@pytest.mark.anyio
async def test_initiate_api_payment_delegates_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeApiProvider()
    monkeypatch.setattr(
        "app.features.payment.services.provider_dispatch.resolve_api_provider",
        lambda provider_code: provider,
    )

    request = InitiationRequest(
        amount=1500,
        currency="XPF",
        order_id="order_123",
        customer_email="client@example.com",
        customer_reference="client_123",
    )

    result = await initiate_api_payment("payzen", request)

    assert provider.last_initiation_request is request
    assert result.provider_code == "fake"
    assert result.form_token == "fake_token"


def test_parse_api_webhook_delegates_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeApiProvider()
    monkeypatch.setattr(
        "app.features.payment.services.provider_dispatch.resolve_api_provider",
        lambda provider_code: provider,
    )

    result = parse_api_webhook("payzen", {"kr-answer": "raw"})

    assert provider.last_payload == {"kr-answer": "raw"}
    assert result.provider_code == "fake"
    assert result.payload == {"parsed": True}
