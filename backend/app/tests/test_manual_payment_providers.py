import pytest

from app.features.payment.providers import (
    SUPPORTED_PROVIDERS,
    ManualCheckProvider,
    ManualTransferProvider,
    get_provider,
)
from app.features.payment.providers.base import (
    InitiationRequest,
    ManualPaymentProvider,
)
from app.features.payment.providers.manual import (
    MANUAL_STATUS_COMPLETED,
    MANUAL_STATUS_FAILED,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_initiation_request(order_id: str = "order-123") -> InitiationRequest:
    return InitiationRequest(
        amount=1500,
        currency="XPF",
        order_id=order_id,
        customer_email="client@example.com",
        customer_reference="user-1",
    )


def test_registry_contains_manual_providers() -> None:
    assert "manual_check" in SUPPORTED_PROVIDERS
    assert "manual_transfer" in SUPPORTED_PROVIDERS
    assert SUPPORTED_PROVIDERS["manual_check"] is ManualCheckProvider
    assert SUPPORTED_PROVIDERS["manual_transfer"] is ManualTransferProvider


def test_get_provider_returns_manual_instances() -> None:
    check_provider = get_provider("manual_check")
    transfer_provider = get_provider("manual_transfer")

    assert isinstance(check_provider, ManualCheckProvider)
    assert isinstance(transfer_provider, ManualTransferProvider)
    assert isinstance(check_provider, ManualPaymentProvider)


@pytest.mark.anyio
async def test_manual_check_register_intent_returns_instructions() -> None:
    provider = ManualCheckProvider()

    result = await provider.register_intent(_make_initiation_request())

    assert result.provider_code == "manual_check"
    assert result.provider_reference == "order-123"
    assert result.instructions is not None
    assert "chèque" in result.instructions.lower()


@pytest.mark.anyio
async def test_manual_transfer_register_intent_returns_instructions() -> None:
    provider = ManualTransferProvider()

    result = await provider.register_intent(_make_initiation_request())

    assert result.provider_code == "manual_transfer"
    assert result.instructions is not None
    assert "virement" in result.instructions.lower()


@pytest.mark.anyio
async def test_manual_provider_confirm_received_returns_completed() -> None:
    provider = ManualCheckProvider()

    result = await provider.confirm_received(
        payment_reference="pay-1",
        admin_user_id="admin-1",
        reference="CHK-42",
    )

    assert result.payment_status == MANUAL_STATUS_COMPLETED
    assert result.provider_reference == "CHK-42"
    assert result.metadata == {"admin_user_id": "admin-1", "reference": "CHK-42"}


@pytest.mark.anyio
async def test_manual_provider_reject_returns_failed() -> None:
    provider = ManualTransferProvider()

    result = await provider.reject(
        payment_reference="pay-2",
        admin_user_id="admin-1",
        reason="Funds not received",
    )

    assert result.payment_status == MANUAL_STATUS_FAILED
    assert result.provider_reference == "pay-2"
    assert result.metadata == {
        "admin_user_id": "admin-1",
        "reason": "Funds not received",
    }
