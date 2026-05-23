from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.features.attachment.storage.local import encode_token


def test_internal_storage_upload_invalid_token_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    response = client.put(
        "/api/v1/internal/storage/garbage.token",
        headers={"content-type": "application/pdf"},
        content=b"data",
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "internal_storage.token.invalid",
            "message": "Invalid token",
            "details": {"reason": "invalid signature"},
        }
    }


def test_internal_storage_upload_wrong_operation_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    token = encode_token(
        key="payments/x/po.pdf",
        operation="get",
        ttl_seconds=60,
        content_type="application/pdf",
    )

    response = client.put(
        f"/api/v1/internal/storage/{token}",
        headers={"content-type": "application/pdf"},
        content=b"data",
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "internal_storage.token.operation_not_allowed",
            "message": "Token does not allow upload",
            "details": {
                "expected": "put",
                "actual": "get",
            },
        }
    }


def test_internal_storage_upload_content_type_mismatch_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    token = encode_token(
        key="payments/x/po.pdf",
        operation="put",
        ttl_seconds=60,
        content_type="application/pdf",
        max_bytes=1024,
    )

    response = client.put(
        f"/api/v1/internal/storage/{token}",
        headers={"content-type": "image/png"},
        content=b"data",
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "internal_storage.content_type.invalid",
            "message": "Content-Type must be application/pdf",
            "details": {
                "expected": "application/pdf",
                "received": "image/png",
            },
        }
    }


def test_internal_storage_upload_too_large_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))

    token = encode_token(
        key="payments/x/po.pdf",
        operation="put",
        ttl_seconds=60,
        content_type="application/pdf",
        max_bytes=3,
    )

    response = client.put(
        f"/api/v1/internal/storage/{token}",
        headers={"content-type": "application/pdf"},
        content=b"data",
    )

    assert response.status_code == 413
    assert response.json() == {
        "error": {
            "code": "internal_storage.file.too_large",
            "message": "File exceeds allowed size",
            "details": {
                "max_bytes": 3,
                "content_length": 4,
            },
        }
    }


def test_internal_storage_disabled_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "s3")

    token = encode_token(
        key="payments/x/po.pdf",
        operation="put",
        ttl_seconds=60,
        content_type="application/pdf",
    )

    response = client.put(
        f"/api/v1/internal/storage/{token}",
        headers={"content-type": "application/pdf"},
        content=b"data",
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "internal_storage.backend.unsupported",
            "message": (
                "Internal storage endpoint is only enabled "
                "with FILE_STORAGE_BACKEND=local"
            ),
            "details": {
                "setting": "FILE_STORAGE_BACKEND",
                "backend": "s3",
                "expected": "local",
            },
        }
    }
