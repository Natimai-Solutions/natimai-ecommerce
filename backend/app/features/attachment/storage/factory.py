from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.features.attachment.storage.base import FileStorage, StorageError


@lru_cache(maxsize=1)
def get_file_storage() -> FileStorage:
    backend = settings.FILE_STORAGE_BACKEND.lower()
    if backend == "s3":
        from app.features.attachment.storage.s3 import S3FileStorage

        return S3FileStorage()
    if backend == "local":
        from app.features.attachment.storage.local import LocalFileStorage

        return LocalFileStorage(root=settings.FILE_STORAGE_LOCAL_ROOT)

    raise StorageError(f"Unknown FILE_STORAGE_BACKEND: {settings.FILE_STORAGE_BACKEND}")


def reset_file_storage_cache() -> None:
    get_file_storage.cache_clear()
