# mypy: disable-error-code="assignment,misc,override"

import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentAttachmentBase(Base):
    """Represents payment attachment base."""

    payment_id: uuid.UUID = Field(
        foreign_key="payments.id",
        nullable=False,
        index=True,
        description="Payment this attachment belongs to",
    )
    file_key: str = Field(
        max_length=512,
        index=True,
        description="Storage key (S3 object key or local file path)",
    )
    filename: str = Field(
        max_length=255,
        description="Original filename provided by the uploader",
    )
    mimetype: str = Field(
        max_length=100,
        description="Declared MIME type — must belong to PAYMENT_ATTACHMENT_ALLOWED_MIME",
    )
    size: int = Field(
        default=0,
        ge=0,
        description="File size in bytes",
    )
    document_type: str = Field(
        max_length=50,
        index=True,
        description="purchase_order | transfer_proof | check_image",
    )
    uploaded_by_user_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        index=True,
    )
    av_scanned: bool = Field(
        default=False,
        description="Whether antivirus scan has been performed",
    )
    av_clean: bool | None = Field(
        default=None,
        description="Result of antivirus scan (None = not scanned)",
    )
    av_signature: str | None = Field(
        default=None,
        max_length=255,
        description="Virus signature reported by ClamAV if infected",
    )


class PaymentAttachmentCreate(PaymentAttachmentBase, BaseCreate):
    """Represents payment attachment create."""

    pass


class PaymentAttachmentUpdate(PaymentAttachmentBase, BaseUpdate):
    """Represents payment attachment update."""

    payment_id: uuid.UUID | None = None
    file_key: str | None = None
    filename: str | None = None
    mimetype: str | None = None
    size: int | None = None
    document_type: str | None = None
    uploaded_by_user_id: uuid.UUID | None = None
    av_scanned: bool | None = None
    av_clean: bool | None = None
    av_signature: str | None = None


class PaymentAttachment(PaymentAttachmentBase, table=True):
    """Represents payment attachment."""

    __tablename__ = "payment_attachments"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
    )


class PaymentAttachmentPublic(PaymentAttachmentBase, BasePublic):
    """Represents payment attachment public."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class PaymentAttachmentsPublic(SQLModel):
    """Represents payment attachments public."""

    data: list[PaymentAttachmentPublic] = Field(default_factory=list)
    count: int = Field(default=0)
