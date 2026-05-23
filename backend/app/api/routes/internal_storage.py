"""Internal endpoints serving HMAC-signed upload/download URLs for the
LocalFileStorage backend. In S3 mode these routes are unused — the client
talks directly to S3.

The endpoints intentionally do not require an authenticated user; the token
itself is the authorization (HMAC-signed with SECRET_KEY, time-limited).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.core.config import settings
from app.core.errors import AppError
from app.features.attachment.storage.local import (
    LocalFileStorage,
    LocalStorageTokenError,
    decode_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/storage", tags=["internal-storage"])


def _storage() -> LocalFileStorage:
    """Execute storage."""
    if settings.FILE_STORAGE_BACKEND.lower() != "local":
        raise AppError(
            code="internal_storage.backend.unsupported",
            status_code=404,
            message=(
                "Internal storage endpoint is only enabled "
                "with FILE_STORAGE_BACKEND=local"
            ),
            details={
                "setting": "FILE_STORAGE_BACKEND",
                "backend": settings.FILE_STORAGE_BACKEND,
                "expected": "local",
            },
        )
    return LocalFileStorage(root=settings.FILE_STORAGE_LOCAL_ROOT)


@router.put("/{token}")
async def upload_via_token(token: str, request: Request) -> Response:
    """Execute upload via token."""
    try:
        body = decode_token(token)
    except LocalStorageTokenError as e:
        raise AppError(
            code="internal_storage.token.invalid",
            status_code=403,
            message="Invalid token",
            details={"reason": str(e)},
        ) from e

    if body.get("op") != "put":
        raise AppError(
            code="internal_storage.token.operation_not_allowed",
            status_code=403,
            message="Token does not allow upload",
            details={
                "expected": "put",
                "actual": body.get("op"),
            },
        )

    declared_ct = body.get("ct")
    if declared_ct and request.headers.get("content-type") != declared_ct:
        raise AppError(
            code="internal_storage.content_type.invalid",
            status_code=400,
            message=f"Content-Type must be {declared_ct}",
            details={
                "expected": declared_ct,
                "received": request.headers.get("content-type"),
            },
        )

    max_bytes = body.get("max")
    content_length = request.headers.get("content-length")
    if max_bytes is not None and content_length is not None:
        try:
            if int(content_length) > int(max_bytes):
                raise AppError(
                    code="internal_storage.file.too_large",
                    status_code=413,
                    message="File exceeds allowed size",
                    details={
                        "max_bytes": int(max_bytes),
                        "content_length": int(content_length),
                    },
                )
        except ValueError as e:
            raise AppError(
                code="internal_storage.content_length.invalid",
                status_code=400,
                message="Invalid Content-Length header",
                details={"content_length": content_length},
            ) from e

    data = await request.body()
    if max_bytes is not None and len(data) > int(max_bytes):
        raise AppError(
            code="internal_storage.file.too_large",
            status_code=413,
            message="File exceeds allowed size",
            details={
                "max_bytes": int(max_bytes),
                "received_bytes": len(data),
            },
        )

    storage = _storage()
    storage.write_bytes(key=body["key"], data=data)
    return Response(status_code=204)


@router.get("/{token}")
async def download_via_token(token: str) -> Response:
    """Execute download via token."""
    try:
        body = decode_token(token)
    except LocalStorageTokenError as e:
        raise AppError(
            code="internal_storage.token.invalid",
            status_code=403,
            message="Invalid token",
            details={"reason": str(e)},
        ) from e

    if body.get("op") != "get":
        raise AppError(
            code="internal_storage.token.operation_not_allowed",
            status_code=403,
            message="Token does not allow download",
            details={
                "expected": "get",
                "actual": body.get("op"),
            },
        )

    storage = _storage()
    data = await storage.get_bytes(key=body["key"])
    return Response(content=data, media_type="application/octet-stream")
