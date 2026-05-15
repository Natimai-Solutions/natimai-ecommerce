
import pytest

from app.features.payment.providers.base import (
    InitiationRequest,
    InitiationResult,
    ManualPaymentProvider,
    ValidationResult,
)
from app.features.payment.services.provider_dispatch import (
    PaymentManualProviderResolutionError,
    register_manual_payment_intent,
    resolve_manual_provider,
)


class _FakeManualProvider(ManualPaymentProvider):
    code = "manual_fake"

    def __init__(self) -> None:
        self.last_initiation_request: InitiationRequest | None = None

    async def register_intent(self, request: InitiationRequest) -> InitiationResult:
        self.last_initiation_request = request
        return InitiationResult(
            provider_code=self.code,
            provider_reference="fake-ref",
            instructions="fake instructions",
        )

    async def confirm_received(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reference: str | None = None,
    ) -> ValidationResult:
        return ValidationResult(provider_code=self.code, payment_status="Completed")

    async def reject(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reason: str,
    ) -> ValidationResult:
        return ValidationResult(provider_code=self.code, payment_status="Failed")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_resolve_manual_provider_returns_manual_instance() -> None:
    provider = resolve_manual_provider("manual_check")

    assert isinstance(provider, ManualPaymentProvider)


def test_resolve_manual_provider_rejects_non_manual_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.features.payment.services.provider_dispatch.get_provider",
        lambda provider_code: object(),
    )

    with pytest.raises(PaymentManualProviderResolutionError):
        resolve_manual_provider("manual_check")


@pytest.mark.anyio
async def test_register_manual_payment_intent_delegates_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeManualProvider()
    monkeypatch.setattr(
        "app.features.payment.services.provider_dispatch.resolve_manual_provider",
        lambda provider_code: provider,
    )

    request = InitiationRequest(
        amount=1000,
        currency="XPF",
        order_id="order-1",
        customer_email="c@example.com",
        customer_reference="u-1",
    )

    result = await register_manual_payment_intent("manual_fake", request)

    assert provider.last_initiation_request is request
    assert result.provider_code == "manual_fake"
    assert result.instructions == "fake instructions"


def test_resolve_api_provider_rejects_manual_provider() -> None:
    from app.features.payment.services.provider_dispatch import (
        PaymentApiProviderResolutionError,
        resolve_api_provider,
    )

    with pytest.raises(PaymentApiProviderResolutionError):
        resolve_api_provider("manual_check")
