from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.routes.internal_storage import download_via_token, upload_via_token
from app.core.errors import AppError
from app.features.attachment.storage.local import encode_token


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _fake_request(*, headers: dict[str, str], body: bytes) -> Mock:
    req = Mock()
    req.headers = headers
    req.body = AsyncMock(return_value=body)
    return req


@pytest.mark.anyio
async def test_upload_via_token_writes_file_locally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    token = encode_token(
        key="payments/x/po.pdf",
        operation="put",
        ttl_seconds=60,
        content_type="application/pdf",
        max_bytes=1024,
    )

    request = _fake_request(
        headers={"content-type": "application/pdf", "content-length": "4"},
        body=b"data",
    )

    response = await upload_via_token(token=token, request=request)

    assert response.status_code == 204
    written = (tmp_path / "payments" / "x" / "po.pdf").read_bytes()
    assert written == b"data"


@pytest.mark.anyio
async def test_upload_via_token_rejects_wrong_content_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    token = encode_token(
        key="payments/x/po.pdf",
        operation="put",
        ttl_seconds=60,
        content_type="application/pdf",
        max_bytes=1024,
    )

    request = _fake_request(
        headers={"content-type": "image/png", "content-length": "4"},
        body=b"data",
    )

    with pytest.raises(AppError) as exc_info:
        await upload_via_token(token=token, request=request)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "internal_storage.content_type.invalid"
    assert exc_info.value.details == {
        "expected": "application/pdf",
        "received": "image/png",
    }


@pytest.mark.anyio
async def test_upload_via_token_rejects_too_large_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    token = encode_token(
        key="payments/x/po.pdf",
        operation="put",
        ttl_seconds=60,
        content_type="application/pdf",
        max_bytes=10,
    )
    big_payload = b"x" * 100
    request = _fake_request(
        headers={"content-type": "application/pdf", "content-length": "100"},
        body=big_payload,
    )

    with pytest.raises(AppError) as exc_info:
        await upload_via_token(token=token, request=request)
    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "internal_storage.file.too_large"
    assert exc_info.value.details == {"max_bytes": 10, "content_length": 100}


@pytest.mark.anyio
async def test_download_via_token_streams_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    file_path = tmp_path / "payments" / "x" / "po.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"PDF_BYTES")

    token = encode_token(key="payments/x/po.pdf", operation="get", ttl_seconds=60)

    response = await download_via_token(token=token)

    assert response.body == b"PDF_BYTES"


@pytest.mark.anyio
async def test_upload_via_token_rejects_bad_signature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    request = _fake_request(
        headers={"content-type": "application/pdf"},
        body=b"data",
    )

    with pytest.raises(AppError) as exc_info:
        await upload_via_token(token="garbage.token", request=request)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "internal_storage.token.invalid"
    assert exc_info.value.details == {"reason": "invalid signature"}


@pytest.mark.anyio
async def test_internal_storage_route_disabled_for_s3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "s3")

    token = encode_token(
        key="payments/x/po.pdf",
        operation="put",
        ttl_seconds=60,
        content_type="application/pdf",
    )
    request = _fake_request(
        headers={"content-type": "application/pdf"},
        body=b"data",
    )

    with pytest.raises(AppError) as exc_info:
        await upload_via_token(token=token, request=request)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "internal_storage.backend.unsupported"
