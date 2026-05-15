"""Internal endpoints serving HMAC-signed upload/download URLs for the
LocalFileStorage backend. In S3 mode these routes are unused — the client
talks directly to S3.

The endpoints intentionally do not require an authenticated user; the token
itself is the authorization (HMAC-signed with SECRET_KEY, time-limited).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.core.config import settings
from app.features.attachment.storage.local import (
    LocalFileStorage,
    LocalStorageTokenError,
    decode_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/storage", tags=["internal-storage"])


def _storage() -> LocalFileStorage:
    if settings.FILE_STORAGE_BACKEND.lower() != "local":
        raise HTTPException(
            404,
            "Internal storage endpoint is only enabled with FILE_STORAGE_BACKEND=local",
        )
    return LocalFileStorage(root=settings.FILE_STORAGE_LOCAL_ROOT)


@router.put("/{token}")
async def upload_via_token(token: str, request: Request) -> Response:
    try:
        body = decode_token(token)
    except LocalStorageTokenError as e:
        raise HTTPException(403, f"Invalid token: {e}") from e

    if body.get("op") != "put":
        raise HTTPException(403, "Token does not allow upload")

    declared_ct = body.get("ct")
    if declared_ct and request.headers.get("content-type") != declared_ct:
        raise HTTPException(
            400,
            f"Content-Type must be {declared_ct}",
        )

    max_bytes = body.get("max")
    content_length = request.headers.get("content-length")
    if max_bytes is not None and content_length is not None:
        try:
            if int(content_length) > int(max_bytes):
                raise HTTPException(413, "File exceeds allowed size")
        except ValueError as e:
            raise HTTPException(400, "Invalid Content-Length header") from e

    data = await request.body()
    if max_bytes is not None and len(data) > int(max_bytes):
        raise HTTPException(413, "File exceeds allowed size")

    storage = _storage()
    storage.write_bytes(key=body["key"], data=data)
    return Response(status_code=204)


@router.get("/{token}")
async def download_via_token(token: str) -> Response:
    try:
        body = decode_token(token)
    except LocalStorageTokenError as e:
        raise HTTPException(403, f"Invalid token: {e}") from e

    if body.get("op") != "get":
        raise HTTPException(403, "Token does not allow download")

    storage = _storage()
    data = await storage.get_bytes(key=body["key"])
    return Response(content=data, media_type="application/octet-stream")
