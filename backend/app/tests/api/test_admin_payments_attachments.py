from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.admin_payments import (
    PaymentApproveRequest,
    PaymentRejectRequest,
    approve_payment,
    get_attachment_download_url,
    reject_payment,
)
from app.features.base.crud import RecordNotFoundError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_attachment import crud_payment_attachment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_attachment import PaymentAttachment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.payment_validation import PaymentValidation
from app.features.payment.providers.document_validated import (
    DOCUMENT_STATUS_APPROVED,
    DOCUMENT_STATUS_REJECTED,
)
from app.features.payment.services import document_payment as dp


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_payment(provider_code: str = "po_public") -> Payment:
    return cast(
        Payment,
        SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            order_id=uuid4(),
            provider_code=provider_code,
            provider_reference=None,
            provider_data=None,
            payment_status_id=None,
            amount=100,
            currency="EUR",
        ),
    )


def _make_admin() -> Any:
    return SimpleNamespace(id=uuid4(), is_superuser=True)


def _make_status(name: str) -> PaymentStatus:
    return cast(PaymentStatus, SimpleNamespace(id=uuid4(), name=name))


def _make_validation(action: str, payment_id: Any) -> PaymentValidation:
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


def _make_attachment(
    payment_id: Any, scanned: bool = True, clean: bool = True
) -> PaymentAttachment:
    return cast(
        PaymentAttachment,
        SimpleNamespace(
            id=uuid4(),
            payment_id=payment_id,
            file_key="payments/abc/po.pdf",
            filename="po.pdf",
            mimetype="application/pdf",
            size=1024,
            document_type="purchase_order",
            uploaded_by_user_id=None,
            av_scanned=scanned,
            av_clean=clean,
            av_signature=None,
            is_active=True,
            created_at=None,
            created_by_id=None,
            modify_at=None,
            modify_by_id=None,
        ),
    )


@pytest.mark.anyio
async def test_approve_payment_routes_document_provider_to_document_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    payment = _make_payment(provider_code="po_public")
    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    approved_status = _make_status(DOCUMENT_STATUS_APPROVED)
    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=approved_status),
    )
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.crud_payment_validation.create_draft",
        AsyncMock(return_value=_make_validation("approve", payment.id)),
    )
    publish = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.outbox_registry.publish",
        publish,
    )

    response = await approve_payment(
        payment_id=payment.id,
        body=PaymentApproveRequest(comment="LGTM"),
        session=session,
        admin=cast(Any, _make_admin()),
    )

    assert response.payment_status_id == approved_status.id
    kwargs = publish.call_args.kwargs
    assert kwargs["event_type"] == dp.EVENT_DOCUMENT_APPROVED


@pytest.mark.anyio
async def test_reject_payment_routes_document_provider_to_document_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    payment = _make_payment(provider_code="po_public")
    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))

    rejected_status = _make_status(DOCUMENT_STATUS_REJECTED)
    monkeypatch.setattr(
        crud_payment_status,
        "get_by_name",
        AsyncMock(return_value=rejected_status),
    )
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.crud_payment_validation.create_draft",
        AsyncMock(return_value=_make_validation("reject", payment.id)),
    )
    publish = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.outbox_registry.publish",
        publish,
    )

    response = await reject_payment(
        payment_id=payment.id,
        body=PaymentRejectRequest(reason="bad signature"),
        session=session,
        admin=cast(Any, _make_admin()),
    )

    assert response.payment_status_id == rejected_status.id
    kwargs = publish.call_args.kwargs
    assert kwargs["event_type"] == dp.EVENT_DOCUMENT_REJECTED


@pytest.mark.anyio
async def test_get_attachment_download_url_returns_presigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = _make_payment()
    attachment = _make_attachment(payment.id, scanned=True, clean=True)

    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))
    monkeypatch.setattr(
        crud_payment_attachment, "read", AsyncMock(return_value=attachment)
    )

    presigned = SimpleNamespace(
        url="https://api.test/internal/storage/token",
        expires_in=300,
    )
    monkeypatch.setattr(
        "app.api.routes.admin_payments.issue_download_url",
        lambda **_kw: presigned,
    )

    response = await get_attachment_download_url(
        payment_id=payment.id,
        attachment_id=attachment.id,
        session=session,
        _admin=cast(Any, _make_admin()),
    )

    assert response.download_url == presigned.url
    assert response.expires_in == 300


@pytest.mark.anyio
async def test_get_attachment_download_url_rejects_infected_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = _make_payment()
    attachment = _make_attachment(payment.id, scanned=True, clean=False)
    attachment.av_signature = "EICAR"

    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))
    monkeypatch.setattr(
        crud_payment_attachment, "read", AsyncMock(return_value=attachment)
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_attachment_download_url(
            payment_id=payment.id,
            attachment_id=attachment.id,
            session=session,
            _admin=cast(Any, _make_admin()),
        )
    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_get_attachment_download_url_returns_404_for_wrong_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = _make_payment()
    attachment = _make_attachment(payment_id=uuid4())  # different payment

    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))
    monkeypatch.setattr(
        crud_payment_attachment, "read", AsyncMock(return_value=attachment)
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_attachment_download_url(
            payment_id=payment.id,
            attachment_id=attachment.id,
            session=session,
            _admin=cast(Any, _make_admin()),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.anyio
async def test_get_attachment_download_url_returns_404_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    payment = _make_payment()

    monkeypatch.setattr(crud_payment, "read", AsyncMock(return_value=payment))
    monkeypatch.setattr(
        crud_payment_attachment,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("nope")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_attachment_download_url(
            payment_id=payment.id,
            attachment_id=uuid4(),
            session=session,
            _admin=cast(Any, _make_admin()),
        )
    assert exc_info.value.status_code == 404
