"""Local-filesystem FileStorage with HMAC-signed URLs for dev and tests.

Presigned URLs point to /internal/storage/{token} which is served by the
internal storage router. The token encodes the key + expiry + operation +
optional content-type guard, signed with SECRET_KEY (HMAC-SHA256).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.features.attachment.storage.base import (
    FileStorage,
    PresignedDownload,
    PresignedUpload,
    StorageError,
)


def _b64url_encode(data: bytes) -> str:
    """Execute b64url encode."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Execute b64url decode."""
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _sign(secret: str, payload: bytes) -> str:
    """Execute sign."""
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return _b64url_encode(digest)


class LocalStorageTokenError(StorageError):
    """Raised when a local-storage token cannot be decoded or verified."""


def encode_token(
    *,
    key: str,
    operation: str,
    ttl_seconds: int,
    content_type: str | None = None,
    max_bytes: int | None = None,
) -> str:
    """Execute encode token."""
    body = {
        "key": key,
        "op": operation,
        "exp": int(time.time()) + ttl_seconds,
    }
    if content_type:
        body["ct"] = content_type
    if max_bytes is not None:
        body["max"] = max_bytes

    payload = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = _sign(settings.SECRET_KEY, payload)
    return f"{_b64url_encode(payload)}.{signature}"


def decode_token(token: str) -> dict[str, Any]:
    """Execute decode token."""
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError as e:
        raise LocalStorageTokenError("malformed token") from e

    payload = _b64url_decode(encoded_payload)
    expected = _sign(settings.SECRET_KEY, payload)
    if not hmac.compare_digest(expected, signature):
        raise LocalStorageTokenError("invalid signature")

    body = json.loads(payload.decode("utf-8"))
    if body.get("exp", 0) < int(time.time()):
        raise LocalStorageTokenError("expired token")
    return body


class LocalFileStorage(FileStorage):
    """Represents local file storage."""

    def __init__(self, root: str, base_url: str | None = None) -> None:
        """Initialize the local file storage instance."""
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.base_url = (
            base_url or f"{settings.FRONTEND_HOST.rstrip('/')}{settings.API_V1_STR}"
        )

    def _path_for(self, key: str) -> Path:
        """Execute path for."""
        safe_key = key.lstrip("/").replace("..", "_")
        return self.root / safe_key

    def generate_upload_url(
        self,
        *,
        key: str,
        content_type: str,
        max_bytes: int,
        ttl_seconds: int,
    ) -> PresignedUpload:
        """Generate upload url."""
        token = encode_token(
            key=key,
            operation="put",
            ttl_seconds=ttl_seconds,
            content_type=content_type,
            max_bytes=max_bytes,
        )
        return PresignedUpload(
            url=f"{self.base_url}/internal/storage/{token}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=ttl_seconds,
        )

    def generate_download_url(
        self,
        *,
        key: str,
        ttl_seconds: int,
        filename: str | None = None,
    ) -> PresignedDownload:
        """Generate download url."""
        token = encode_token(key=key, operation="get", ttl_seconds=ttl_seconds)
        suffix = f"?filename={filename}" if filename else ""
        return PresignedDownload(
            url=f"{self.base_url}/internal/storage/{token}{suffix}",
            expires_in=ttl_seconds,
        )

    async def head(self, *, key: str) -> dict[str, Any] | None:
        """Execute head."""
        path = self._path_for(key)
        if not path.is_file():
            return None
        return {"size": path.stat().st_size}

    async def get_bytes(self, *, key: str) -> bytes:
        """Get bytes."""
        path = self._path_for(key)
        if not path.is_file():
            raise StorageError(f"Object {key} not found")
        return path.read_bytes()

    async def delete(self, *, key: str) -> None:
        """Execute delete."""
        path = self._path_for(key)
        try:
            os.remove(path)
        except FileNotFoundError:
            return

    def write_bytes(self, *, key: str, data: bytes) -> None:
        """Execute write bytes."""
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
