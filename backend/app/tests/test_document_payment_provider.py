import pytest

from app.features.payment.providers import (
    SUPPORTED_PROVIDERS,
    PublicPurchaseOrderProvider,
    get_provider,
)
from app.features.payment.providers.base import (
    DocumentValidatedProvider,
    InitiationRequest,
)
from app.features.payment.providers.document_validated import (
    DOCUMENT_STATUS_APPROVED,
    DOCUMENT_STATUS_REJECTED,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _request(order_id: str = "order-1") -> InitiationRequest:
    return InitiationRequest(
        amount=10_000,
        currency="XPF",
        order_id=order_id,
        customer_email="c@example.com",
        customer_reference="u-1",
    )


def test_registry_contains_po_public_provider() -> None:
    assert "po_public" in SUPPORTED_PROVIDERS
    assert SUPPORTED_PROVIDERS["po_public"] is PublicPurchaseOrderProvider


def test_get_provider_returns_document_validated_instance() -> None:
    provider = get_provider("po_public")
    assert isinstance(provider, PublicPurchaseOrderProvider)
    assert isinstance(provider, DocumentValidatedProvider)


@pytest.mark.anyio
async def test_po_provider_register_intent_returns_instructions() -> None:
    provider = PublicPurchaseOrderProvider()

    result = await provider.register_intent(_request())

    assert result.provider_code == "po_public"
    assert result.provider_reference == "order-1"
    assert result.instructions is not None
    assert "bon de commande" in result.instructions.lower()


@pytest.mark.anyio
async def test_po_provider_attach_document_returns_attachment_result() -> None:
    provider = PublicPurchaseOrderProvider()

    result = await provider.attach_document(
        payment_reference="pay-1",
        file_key="payments/abc/po.pdf",
        filename="po.pdf",
    )

    assert result.file_key == "payments/abc/po.pdf"
    assert result.filename == "po.pdf"
    assert result.metadata == {"payment_reference": "pay-1"}


@pytest.mark.anyio
async def test_po_provider_approve_returns_completed() -> None:
    provider = PublicPurchaseOrderProvider()

    result = await provider.approve(
        payment_reference="pay-1",
        admin_user_id="admin-1",
        comment="LGTM",
    )

    assert result.payment_status == DOCUMENT_STATUS_APPROVED
    assert result.metadata == {"admin_user_id": "admin-1", "comment": "LGTM"}


@pytest.mark.anyio
async def test_po_provider_reject_returns_failed() -> None:
    provider = PublicPurchaseOrderProvider()

    result = await provider.reject(
        payment_reference="pay-1",
        admin_user_id="admin-1",
        reason="missing signature",
    )

    assert result.payment_status == DOCUMENT_STATUS_REJECTED
    assert result.metadata == {
        "admin_user_id": "admin-1",
        "reason": "missing signature",
    }
