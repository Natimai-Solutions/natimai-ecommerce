"""S3-backed FileStorage. boto3 is imported lazily so non-S3 deployments
(and tests with mocked storage) do not require the dependency at import time.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.features.attachment.storage.base import (
    FileStorage,
    PresignedDownload,
    PresignedUpload,
    StorageError,
)


def _build_s3_client() -> Any:
    try:
        import boto3
    except ImportError as e:
        raise StorageError(
            "boto3 is required for the S3 storage backend. "
            "Add it to your dependencies (already in pyproject.toml — run `uv sync`)."
        ) from e

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_KEY_ID,
        region_name=settings.S3_REGION,
    )


class S3FileStorage(FileStorage):
    def __init__(
        self,
        *,
        bucket: str | None = None,
        client: Any | None = None,
    ) -> None:
        resolved_bucket = bucket or settings.S3_BUCKET_NAME
        if not resolved_bucket:
            raise StorageError("S3_BUCKET_NAME is required for the S3 backend")

        self.bucket = resolved_bucket
        self.client = client or _build_s3_client()

    def generate_upload_url(
        self,
        *,
        key: str,
        content_type: str,
        max_bytes: int,
        ttl_seconds: int,
    ) -> PresignedUpload:
        url = self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=ttl_seconds,
        )
        return PresignedUpload(
            url=url,
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
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        url = self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params=params,
            ExpiresIn=ttl_seconds,
        )
        return PresignedDownload(url=url, expires_in=ttl_seconds)

    async def head(self, *, key: str) -> dict[str, Any] | None:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        return {
            "size": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
        }

    async def get_bytes(self, *, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            raise StorageError(f"Failed to fetch S3 object {key}: {e}") from e
        body = response["Body"]
        return body.read()

    async def delete(self, *, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
