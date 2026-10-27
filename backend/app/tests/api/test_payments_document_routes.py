from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.payments import (
    DocumentUploadedRequest,
    PaymentsInitiateRequest,
    UploadDocumentRequest,
    confirm_document_uploaded,
    initiate_payment,
    issue_document_upload_url,
)
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_attachment import PaymentAttachment


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_payment(provider_code: str = "po_public", user_id: Any = None) -> Payment:
    return cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            payment_method_id=None,
            provider_code=provider_code,
            provider_reference=None,
            provider_data=None,
            payment_status_id=None,
            order_id=uuid4(),
            user_id=user_id or uuid4(),
            amount=Decimal("500"),
            currency="EUR",
        ),
    )


def _make_user(user_id: Any = None) -> Any:
    return SimpleNamespace(
        id=user_id or uuid4(),
        email="client@example.com",
        full_name="Jane Doe",
        price_group_id=None,
    )


@pytest.mark.anyio
async def test_payments_initiate_dispatches_po_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    payment = _make_payment()

    monkeypatch.setattr(
        crud_payment,
        "create_payment_with_log",
        AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.resolve_provider_code_for_payment_method",
        AsyncMock(return_value="po_public"),
    )

    register_mock = AsyncMock(return_value=payment)
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.register_document_intent",
        register_mock,
    )
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.check_payment_method_eligible",
        AsyncMock(return_value=True),
    )
    # No shop-specific wording: the provider's text applies.
    monkeypatch.setattr(
        "app.features.payment.services.payment_initiation.shop_instructions",
        AsyncMock(return_value=None),
    )
    # Order revalidation is covered by test_payments_initiate_order_guard.py;
    # this test focuses on the document-provider dispatch.
    monkeypatch.setattr(
        "app.api.routes.payments._validate_order_for_initiation",
        AsyncMock(return_value=None),
    )

    request = PaymentsInitiateRequest(
        payment_method_id=uuid4(),
        amount=Decimal("500.00"),
        currency="EUR",
        order_id=payment.order_id,
    )
    current_user = cast(Any, _make_user(user_id=payment.user_id))

    response = await initiate_payment(
        session=session, request=request, current_user=current_user
    )

    assert response.provider_code == "po_public"
    assert response.instructions is not None
    assert "bon de commande" in response.instructions.lower()
    register_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_issue_document_upload_url_returns_presigned_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _make_payment()
    user = _make_user(user_id=payment.user_id)

    session = AsyncMock()
    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    intent = SimpleNamespace(
        payment_id=payment.id,
        file_key=f"payments/{payment.id}/purchase_order/abc-po.pdf",
        upload=SimpleNamespace(
            url="https://api.test/internal/storage/tok",
            method="PUT",
            headers={"Content-Type": "application/pdf"},
            expires_in=300,
        ),
        max_bytes=10 * 1024 * 1024,
        allowed_mime=["application/pdf"],
    )
    monkeypatch.setattr(
        "app.api.routes.payments.issue_upload_intent", lambda **_kw: intent
    )

    response = await issue_document_upload_url(
        payment_id=payment.id,
        body=UploadDocumentRequest(filename="po.pdf", mimetype="application/pdf"),
        session=session,
        current_user=cast(Any, user),
    )

    assert response.upload_url.startswith("https://api.test")
    assert response.upload_method == "PUT"
    assert response.allowed_mime == ["application/pdf"]


@pytest.mark.anyio
async def test_issue_document_upload_url_rejects_non_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _make_payment()
    other_user = _make_user()  # different id

    session = AsyncMock()
    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    with pytest.raises(AppError) as exc_info:
        await issue_document_upload_url(
            payment_id=payment.id,
            body=UploadDocumentRequest(filename="po.pdf", mimetype="application/pdf"),
            session=session,
            current_user=cast(Any, other_user),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "payment.not_found"


@pytest.mark.anyio
async def test_issue_document_upload_url_rejects_non_document_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _make_payment(provider_code="payzen")
    user = _make_user(user_id=payment.user_id)

    session = AsyncMock()
    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    with pytest.raises(AppError) as exc_info:
        await issue_document_upload_url(
            payment_id=payment.id,
            body=UploadDocumentRequest(filename="po.pdf", mimetype="application/pdf"),
            session=session,
            current_user=cast(Any, user),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "payment.not_document_validated"


@pytest.mark.anyio
async def test_issue_document_upload_url_returns_404_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    monkeypatch.setattr(
        crud_payment, "read", AsyncMock(side_effect=RecordNotFoundError("missing"))
    )

    with pytest.raises(AppError) as exc_info:
        await issue_document_upload_url(
            payment_id=uuid4(),
            body=UploadDocumentRequest(filename="po.pdf", mimetype="application/pdf"),
            session=session,
            current_user=cast(Any, _make_user()),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "payment.not_found"


@pytest.mark.anyio
async def test_confirm_document_uploaded_registers_attachment_and_marks_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _make_payment()
    user = _make_user(user_id=payment.user_id)

    session = AsyncMock()
    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    attachment = cast(
        PaymentAttachment,
        SimpleNamespace(
            id=uuid4(),
            file_key="payments/abc/po.pdf",
            filename="po.pdf",
            mimetype="application/pdf",
        ),
    )
    register_attachment = AsyncMock(return_value=attachment)
    monkeypatch.setattr(
        "app.api.routes.payments.register_uploaded_attachment",
        register_attachment,
    )

    mark_uploaded = AsyncMock(return_value=payment)
    monkeypatch.setattr("app.api.routes.payments.mark_document_uploaded", mark_uploaded)

    response = await confirm_document_uploaded(
        payment_id=payment.id,
        body=DocumentUploadedRequest(
            file_key=f"payments/{payment.id}/purchase_order/po.pdf",
            filename="po.pdf",
            mimetype="application/pdf",
        ),
        session=session,
        current_user=cast(Any, user),
    )

    assert response.payment_id == payment.id
    assert response.attachment_id == attachment.id
    register_attachment.assert_awaited_once()
    mark_uploaded.assert_awaited_once()
    session.commit.assert_awaited_once()
