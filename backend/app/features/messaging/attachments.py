"""Files joined to the messaging (photos of a damaged parcel, an invoice…).

Every upload goes through the same steps, server side:

1. size cap (``MAX_BYTES``, before any conversion) and count cap per
   conversation;
2. the **type is read from the bytes**, never from the name or the declared
   type: PDF, JPEG, PNG, WebP, HEIC / HEIF (iPhone photos); anything else is
   refused (415);
3. antivirus scan of the raw bytes (same scanner as the media library and
   the payment attachments): an infected file is refused, nothing is stored;
4. an image is **re-encoded**: orientation applied, every metadata dropped —
   a phone photo often carries the GPS position of the customer's home —,
   at most ``MAX_SIDE`` pixels; a HEIC photo becomes a JPEG;
5. stored under ``messaging/{conversation_id}/{attachment_id}``: the name the
   customer gave is never part of the key.

Only clean files exist, so a download never serves an unscanned file.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import re
import unicodedata
import uuid
from dataclasses import dataclass

import anyio
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.attachment.antivirus.factory import get_antivirus_scanner
from app.features.attachment.storage.factory import get_file_storage
from app.features.messaging.models import Conversation, ConversationAttachment

MAX_BYTES = 5 * 1024 * 1024
MAX_PER_CONVERSATION = 20
MAX_SIDE = 2560
MAX_PIXELS = 50_000_000
JPEG_QUALITY = 85
KEY_PREFIX = "messaging"

#: ftyp brands of HEIC / HEIF images.
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1")


def detect_type(data: bytes) -> str | None:
    """The MIME type the bytes really are, among the accepted ones."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic"
    return None


def safe_filename(name: str | None, mime: str) -> str:
    """A name fit for a ``Content-Disposition`` header: no path, no control
    character, a sane length, the extension of the stored type."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFC", base)
    base = re.sub(r"[\x00-\x1f\x7f\"]", "", base).strip(" .") or "fichier"
    stem = base.rsplit(".", 1)[0][:120] or "fichier"
    extension = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }[mime]
    return f"{stem}.{extension}"


def ascii_filename(name: str) -> str:
    """The ASCII fallback of ``filename=`` (the UTF-8 one goes in ``filename*``)."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._ -]", "_", folded) or "fichier"


@dataclass(frozen=True)
class Prepared:
    data: bytes
    mime: str


def _register_heif() -> None:
    from pillow_heif import register_heif_opener

    register_heif_opener()


def _reencode(data: bytes, mime: str) -> Prepared:
    """Re-encode an image without metadata (runs in a thread)."""
    if mime == "image/heic":
        _register_heif()
    try:
        with Image.open(io.BytesIO(data)) as source:
            # Read from the header, before any decoding: Pillow only refuses
            # twice its own limit, and a 9900×9900 flat PNG of 300 KB would
            # be decoded whole (≈ 300 MB). Pillow's process-wide limit is
            # left as it is (the media library shares it).
            if source.width * source.height > MAX_PIXELS:
                raise ValueError("image too large")
            image = ImageOps.exif_transpose(source)
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            has_alpha = image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            )
            out = io.BytesIO()
            if mime == "image/png" or (mime == "image/webp" and has_alpha):
                image.save(out, format="PNG", optimize=True)
                return Prepared(out.getvalue(), "image/png")
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return Prepared(out.getvalue(), "image/jpeg")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise AppError(
            code="messaging.attachment.unreadable",
            status_code=400,
            message="This image cannot be read.",
            details={},
        ) from exc


async def prepare(data: bytes) -> Prepared:
    """Checks, antivirus and re-encoding of an upload (see the module doc)."""
    if not data:
        raise AppError(
            code="messaging.attachment.empty",
            status_code=400,
            message="The file is empty.",
            details={},
        )
    if len(data) > MAX_BYTES:
        raise AppError(
            code="messaging.attachment.too_large",
            status_code=413,
            message="The file is larger than {max_mb} MB.",
            details={"max_mb": MAX_BYTES // (1024 * 1024)},
        )
    mime = detect_type(data)
    if mime is None:
        raise AppError(
            code="messaging.attachment.type",
            status_code=415,
            message="Only PDF files and photos (JPEG, PNG, WebP, HEIC) are accepted.",
            details={},
        )
    scan = await get_antivirus_scanner().scan_bytes(data)
    if not scan.is_clean:
        raise AppError(
            code="messaging.attachment.infected",
            status_code=400,
            message="The file was rejected by the antivirus.",
            details={},
        )
    if mime == "application/pdf":
        return Prepared(data, mime)
    return await anyio.to_thread.run_sync(_reencode, data, mime)


async def store(
    session: AsyncSession,
    conversation: Conversation,
    *,
    message_id: uuid.UUID,
    filename: str | None,
    prepared: Prepared,
    now: datetime.datetime,
) -> ConversationAttachment:
    """Store a prepared file and record it (no commit)."""
    count = (
        await session.execute(
            select(func.count())
            .select_from(ConversationAttachment)
            .where(col(ConversationAttachment.conversation_id) == conversation.id)
        )
    ).scalar_one()
    if int(count) >= MAX_PER_CONVERSATION:
        raise AppError(
            code="messaging.attachment.too_many",
            status_code=409,
            message="A conversation holds at most {max} files.",
            details={"max": MAX_PER_CONVERSATION},
        )
    attachment_id = uuid.uuid4()
    key = f"{KEY_PREFIX}/{conversation.id}/{attachment_id}"
    await get_file_storage().put_bytes(
        key=key, data=prepared.data, content_type=prepared.mime
    )
    attachment = ConversationAttachment(
        id=attachment_id,
        conversation_id=conversation.id,
        message_id=message_id,
        filename=safe_filename(filename, prepared.mime),
        mime=prepared.mime,
        size=len(prepared.data),
        sha256=hashlib.sha256(prepared.data).hexdigest(),
        object_key=key,
        created_at=now,
    )
    session.add(attachment)
    return attachment


async def delete_objects(
    session: AsyncSession, conversation_ids: list[uuid.UUID]
) -> None:
    """Remove the stored files of these conversations (best effort per file):
    called before their rows are deleted."""
    if not conversation_ids:
        return
    keys = (
        await session.exec(
            select(ConversationAttachment.object_key).where(
                col(ConversationAttachment.conversation_id).in_(conversation_ids)
            )
        )
    ).all()
    storage = get_file_storage()
    for key in keys:
        try:
            await storage.delete(key=key)
        except Exception:  # noqa: BLE001 - a missing file is already gone
            continue


async def read(attachment: ConversationAttachment) -> bytes:
    return await get_file_storage().get_bytes(key=attachment.object_key)


__all__ = [
    "MAX_BYTES",
    "MAX_PER_CONVERSATION",
    "Prepared",
    "ascii_filename",
    "delete_objects",
    "detect_type",
    "prepare",
    "read",
    "safe_filename",
    "store",
]
