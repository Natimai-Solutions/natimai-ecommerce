from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class StorageError(RuntimeError):
    """Generic file storage error."""


@dataclass(slots=True)
class PresignedUpload:
    url: str
    method: str = "PUT"
    headers: dict[str, str] = field(default_factory=dict)
    fields: dict[str, str] = field(default_factory=dict)
    expires_in: int = 0


@dataclass(slots=True)
class PresignedDownload:
    url: str
    expires_in: int = 0


class FileStorage(ABC):
    @abstractmethod
    def generate_upload_url(
        self,
        *,
        key: str,
        content_type: str,
        max_bytes: int,
        ttl_seconds: int,
    ) -> PresignedUpload:
        """Return upload URL the client can PUT/POST to."""

    @abstractmethod
    def generate_download_url(
        self,
        *,
        key: str,
        ttl_seconds: int,
        filename: str | None = None,
    ) -> PresignedDownload:
        """Return time-limited download URL for an admin to fetch the file."""

    @abstractmethod
    async def head(self, *, key: str) -> dict[str, Any] | None:
        """Return basic metadata (size, content_type) or None if missing."""

    @abstractmethod
    async def get_bytes(self, *, key: str) -> bytes:
        """Return full file contents — only for AV scan / internal use."""

    @abstractmethod
    async def delete(self, *, key: str) -> None:
        """Remove the object."""
