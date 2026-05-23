"""Attachment service — owns upload URL generation, persistence, and AV scan
orchestration for payment-related documents.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.attachment.antivirus.factory import get_antivirus_scanner
from app.features.attachment.storage.base import PresignedDownload, PresignedUpload
from app.features.attachment.storage.factory import get_file_storage
from app.features.payment.crud.payment_attachment import crud_payment_attachment
from app.features.payment.models.payment_attachment import (
    PaymentAttachment,
    PaymentAttachmentCreate,
)
from app.features.user.models.user import User

DOCUMENT_TYPE_PURCHASE_ORDER = "purchase_order"


class AttachmentValidationError(ValueError):
    """Invalid upload metadata (MIME, size, etc.)."""


@dataclass(slots=True)
class UploadIntent:
    """Represents upload intent."""

    payment_id: uuid.UUID
    file_key: str
    upload: PresignedUpload
    max_bytes: int
    allowed_mime: list[str]


def _validate_mime(mimetype: str) -> None:
    """Validate mime."""
    allowed = settings.PAYMENT_ATTACHMENT_ALLOWED_MIME
    if mimetype not in allowed:
        raise AttachmentValidationError(
            f"MIME type '{mimetype}' is not allowed. Allowed: {', '.join(allowed)}"
        )


def _build_file_key(*, payment_id: uuid.UUID, document_type: str, filename: str) -> str:
    """Build file key."""
    return f"payments/{payment_id}/{document_type}/{uuid.uuid4()}-{filename}"


def issue_upload_intent(
    *,
    payment_id: uuid.UUID,
    filename: str,
    mimetype: str,
    document_type: str = DOCUMENT_TYPE_PURCHASE_ORDER,
) -> UploadIntent:
    """Execute issue upload intent."""
    _validate_mime(mimetype)

    file_key = _build_file_key(
        payment_id=payment_id,
        document_type=document_type,
        filename=filename,
    )

    storage = get_file_storage()
    presigned = storage.generate_upload_url(
        key=file_key,
        content_type=mimetype,
        max_bytes=settings.PAYMENT_ATTACHMENT_MAX_BYTES,
        ttl_seconds=settings.FILE_STORAGE_PRESIGNED_TTL_SECONDS,
    )

    return UploadIntent(
        payment_id=payment_id,
        file_key=file_key,
        upload=presigned,
        max_bytes=settings.PAYMENT_ATTACHMENT_MAX_BYTES,
        allowed_mime=list(settings.PAYMENT_ATTACHMENT_ALLOWED_MIME),
    )


async def register_uploaded_attachment(
    session: AsyncSession,
    *,
    payment_id: uuid.UUID,
    file_key: str,
    filename: str,
    mimetype: str,
    document_type: str,
    user: User | None,
) -> PaymentAttachment:
    """Execute register uploaded attachment."""
    _validate_mime(mimetype)

    storage = get_file_storage()
    head = await storage.head(key=file_key)
    if head is None:
        raise AttachmentValidationError(
            f"No file found at storage key {file_key} — was the upload completed?"
        )

    size = int(head.get("size") or 0)
    if size <= 0:
        raise AttachmentValidationError("Uploaded file is empty")
    if size > settings.PAYMENT_ATTACHMENT_MAX_BYTES:
        raise AttachmentValidationError(
            f"Uploaded file size {size} exceeds the limit of "
            f"{settings.PAYMENT_ATTACHMENT_MAX_BYTES} bytes"
        )

    attachment = await crud_payment_attachment.create_draft(
        session=session,
        data=PaymentAttachmentCreate(
            payment_id=payment_id,
            file_key=file_key,
            filename=filename,
            mimetype=mimetype,
            size=size,
            document_type=document_type,
            uploaded_by_user_id=user.id if user else None,
        ),
        user=user,
    )
    return attachment


async def scan_attachment_now(
    session: AsyncSession,
    *,
    attachment: PaymentAttachment,
) -> PaymentAttachment:
    """Execute scan attachment now."""
    storage = get_file_storage()
    scanner = get_antivirus_scanner()

    data = await storage.get_bytes(key=attachment.file_key)
    result = await scanner.scan_bytes(data)

    attachment.av_scanned = True
    attachment.av_clean = result.is_clean
    attachment.av_signature = result.signature
    session.add(attachment)

    if not result.is_clean:
        try:
            await storage.delete(key=attachment.file_key)
        except Exception:
            pass

    return attachment


def issue_download_url(
    *, file_key: str, filename: str | None = None
) -> PresignedDownload:
    """Execute issue download url."""
    storage = get_file_storage()
    return storage.generate_download_url(
        key=file_key,
        ttl_seconds=settings.FILE_STORAGE_PRESIGNED_TTL_SECONDS,
        filename=filename,
    )
