import time
from pathlib import Path

import pytest

from app.features.attachment.storage.local import (
    LocalFileStorage,
    LocalStorageTokenError,
    decode_token,
    encode_token,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_encode_decode_token_roundtrip() -> None:
    token = encode_token(
        key="payments/abc/po.pdf",
        operation="put",
        ttl_seconds=60,
        content_type="application/pdf",
        max_bytes=1024,
    )
    body = decode_token(token)

    assert body["key"] == "payments/abc/po.pdf"
    assert body["op"] == "put"
    assert body["ct"] == "application/pdf"
    assert body["max"] == 1024


def test_decode_token_rejects_tampered_signature() -> None:
    token = encode_token(key="k", operation="put", ttl_seconds=60)
    body, _sig = token.split(".", 1)
    tampered = f"{body}.tampered_signature_value"

    with pytest.raises(LocalStorageTokenError):
        decode_token(tampered)


def test_decode_token_rejects_expired_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = encode_token(key="k", operation="put", ttl_seconds=1)
    # Advance "now" beyond expiry
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 10)

    with pytest.raises(LocalStorageTokenError):
        decode_token(token)


@pytest.mark.anyio
async def test_local_storage_write_and_read(tmp_path: Path) -> None:
    storage = LocalFileStorage(root=str(tmp_path))

    storage.write_bytes(key="payments/x/file.pdf", data=b"PDF-DATA")

    head = await storage.head(key="payments/x/file.pdf")
    assert head is not None
    assert head["size"] == len(b"PDF-DATA")

    data = await storage.get_bytes(key="payments/x/file.pdf")
    assert data == b"PDF-DATA"


@pytest.mark.anyio
async def test_local_storage_delete(tmp_path: Path) -> None:
    storage = LocalFileStorage(root=str(tmp_path))
    storage.write_bytes(key="payments/y/file.pdf", data=b"x")

    await storage.delete(key="payments/y/file.pdf")

    head = await storage.head(key="payments/y/file.pdf")
    assert head is None


def test_local_storage_presigned_upload_url(tmp_path: Path) -> None:
    storage = LocalFileStorage(root=str(tmp_path), base_url="https://api.local")

    presigned = storage.generate_upload_url(
        key="payments/x/file.pdf",
        content_type="application/pdf",
        max_bytes=2048,
        ttl_seconds=60,
    )

    assert presigned.method == "PUT"
    assert presigned.headers["Content-Type"] == "application/pdf"
    assert presigned.url.startswith("https://api.local/internal/storage/")


def test_local_storage_presigned_download_url(tmp_path: Path) -> None:
    storage = LocalFileStorage(root=str(tmp_path), base_url="https://api.local")

    presigned = storage.generate_download_url(
        key="payments/x/file.pdf",
        ttl_seconds=60,
        filename="bon-de-commande.pdf",
    )

    assert presigned.url.startswith("https://api.local/internal/storage/")
    assert "filename=bon-de-commande.pdf" in presigned.url
