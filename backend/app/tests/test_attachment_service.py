from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.features.attachment import service as attachment_service
from app.features.attachment.storage.base import PresignedUpload
from app.features.payment.models.payment_attachment import PaymentAttachment


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeStorage:
    def __init__(self) -> None:
        self.head_calls: list[str] = []
        self.head_result: dict[str, Any] | None = {"size": 1024}

    def generate_upload_url(
        self,
        *,
        key: str,
        content_type: str,
        max_bytes: int,
        ttl_seconds: int,
    ) -> PresignedUpload:
        return PresignedUpload(
            url=f"https://test.local/upload/{key}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=ttl_seconds,
        )

    async def head(self, *, key: str) -> dict[str, Any] | None:
        self.head_calls.append(key)
        return self.head_result

    async def get_bytes(self, *, key: str) -> bytes:
        return b"data"

    async def delete(self, *, key: str) -> None:
        pass


def test_issue_upload_intent_rejects_unsupported_mime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.features.attachment.service.get_file_storage",
        lambda: _FakeStorage(),
    )

    with pytest.raises(attachment_service.AttachmentValidationError):
        attachment_service.issue_upload_intent(
            payment_id=uuid4(),
            filename="virus.exe",
            mimetype="application/x-msdownload",
        )


def test_issue_upload_intent_returns_presigned_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeStorage()
    monkeypatch.setattr(
        "app.features.attachment.service.get_file_storage", lambda: fake
    )

    payment_id = uuid4()
    intent = attachment_service.issue_upload_intent(
        payment_id=payment_id,
        filename="po.pdf",
        mimetype="application/pdf",
    )

    assert intent.payment_id == payment_id
    assert intent.upload.method == "PUT"
    assert intent.upload.headers["Content-Type"] == "application/pdf"
    assert "application/pdf" in intent.allowed_mime
    assert intent.file_key.startswith(f"payments/{payment_id}/purchase_order/")
    assert intent.file_key.endswith("-po.pdf")


@pytest.mark.anyio
async def test_register_uploaded_attachment_persists_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeStorage()
    monkeypatch.setattr(
        "app.features.attachment.service.get_file_storage", lambda: fake
    )

    saved = cast(
        PaymentAttachment,
        SimpleNamespace(
            id=uuid4(),
            file_key="payments/abc/po.pdf",
            filename="po.pdf",
            mimetype="application/pdf",
            size=1024,
        ),
    )
    monkeypatch.setattr(
        "app.features.attachment.service.crud_payment_attachment.create_draft",
        AsyncMock(return_value=saved),
    )

    session = AsyncMock()
    user = cast(Any, SimpleNamespace(id=uuid4()))
    payment_id = uuid4()

    result = await attachment_service.register_uploaded_attachment(
        session,
        payment_id=payment_id,
        file_key="payments/abc/po.pdf",
        filename="po.pdf",
        mimetype="application/pdf",
        document_type="purchase_order",
        user=user,
    )

    assert result is saved
    assert fake.head_calls == ["payments/abc/po.pdf"]


@pytest.mark.anyio
async def test_register_uploaded_attachment_rejects_missing_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeStorage()
    fake.head_result = None
    monkeypatch.setattr(
        "app.features.attachment.service.get_file_storage", lambda: fake
    )

    session = AsyncMock()

    with pytest.raises(attachment_service.AttachmentValidationError):
        await attachment_service.register_uploaded_attachment(
            session,
            payment_id=uuid4(),
            file_key="payments/missing/po.pdf",
            filename="po.pdf",
            mimetype="application/pdf",
            document_type="purchase_order",
            user=None,
        )


@pytest.mark.anyio
async def test_register_uploaded_attachment_rejects_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeStorage()
    fake.head_result = {"size": 10**9}  # 1 GB — way above limit
    monkeypatch.setattr(
        "app.features.attachment.service.get_file_storage", lambda: fake
    )

    session = AsyncMock()

    with pytest.raises(attachment_service.AttachmentValidationError) as exc_info:
        await attachment_service.register_uploaded_attachment(
            session,
            payment_id=uuid4(),
            file_key="payments/big/po.pdf",
            filename="po.pdf",
            mimetype="application/pdf",
            document_type="purchase_order",
            user=None,
        )
    assert "exceeds the limit" in str(exc_info.value)


@pytest.mark.anyio
async def test_scan_attachment_now_marks_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeStorage()
    monkeypatch.setattr(
        "app.features.attachment.service.get_file_storage", lambda: fake
    )

    scanner = Mock()
    scanner.scan_bytes = AsyncMock(
        return_value=SimpleNamespace(is_clean=True, signature=None)
    )
    monkeypatch.setattr(
        "app.features.attachment.service.get_antivirus_scanner",
        lambda: scanner,
    )

    session = AsyncMock()
    session.add = Mock()
    attachment = cast(
        PaymentAttachment,
        SimpleNamespace(
            id=uuid4(),
            file_key="payments/abc/po.pdf",
            av_scanned=False,
            av_clean=None,
            av_signature=None,
        ),
    )

    result = await attachment_service.scan_attachment_now(
        session, attachment=attachment
    )

    assert result.av_scanned is True
    assert result.av_clean is True
    assert result.av_signature is None


@pytest.mark.anyio
async def test_scan_attachment_now_marks_infected_and_deletes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeStorage()
    delete_mock = AsyncMock()
    fake.delete = delete_mock  # type: ignore[method-assign]
    monkeypatch.setattr(
        "app.features.attachment.service.get_file_storage", lambda: fake
    )

    scanner = Mock()
    scanner.scan_bytes = AsyncMock(
        return_value=SimpleNamespace(is_clean=False, signature="EICAR")
    )
    monkeypatch.setattr(
        "app.features.attachment.service.get_antivirus_scanner",
        lambda: scanner,
    )

    session = AsyncMock()
    session.add = Mock()
    attachment = cast(
        PaymentAttachment,
        SimpleNamespace(
            id=uuid4(),
            file_key="payments/abc/virus.pdf",
            av_scanned=False,
            av_clean=None,
            av_signature=None,
        ),
    )

    result = await attachment_service.scan_attachment_now(
        session, attachment=attachment
    )

    assert result.av_clean is False
    assert result.av_signature == "EICAR"
    delete_mock.assert_awaited_once()
