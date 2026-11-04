"""Document-validated payment orchestration.

Mirrors the structure of `manual_payment.py` for symmetry: a single module
that owns state transitions, audit-trail entries (PaymentValidation) and
outbox event publication for document providers (currently PO public).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.crud.payment_validation import crud_payment_validation
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_attachment import PaymentAttachment
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
)
from app.features.payment.models.payment_validation import (
    PaymentValidation,
    PaymentValidationCreate,
)
from app.features.payment.providers.document_validated import (
    DOCUMENT_STATUS_APPROVED,
    DOCUMENT_STATUS_DOCUMENT_REQUIRED,
    DOCUMENT_STATUS_DOCUMENT_UPLOADED,
    DOCUMENT_STATUS_REJECTED,
)
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry

EVENT_DOCUMENT_REQUIRED = "payment.document_required"
EVENT_DOCUMENT_UPLOADED = "payment.document_uploaded"
EVENT_DOCUMENT_INFECTED = "payment.document_infected"
EVENT_DOCUMENT_APPROVED = "payment.captured"
EVENT_DOCUMENT_REJECTED = "payment.rejected"

ACTION_REGISTER_INTENT = "register_intent"
ACTION_ATTACH_DOCUMENT = "attach_document"
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"


class PaymentNotDocumentValidatedError(RuntimeError):
    """Raised when a payment's provider does not match a document workflow."""


class PaymentDocumentMissingError(RuntimeError):
    """Raised when a document payment is approved before any usable document
    (uploaded, active, not flagged infected) is attached to it."""


async def has_usable_document(session: AsyncSession, payment_id: uuid.UUID) -> bool:
    """Whether the payment carries a document the admin can rely on: active
    and not flagged infected by the antivirus."""
    row = (
        await session.exec(
            select(PaymentAttachment.id)
            .where(
                col(PaymentAttachment.payment_id) == payment_id,
                col(PaymentAttachment.is_active).is_(True),
                col(PaymentAttachment.av_clean).is_not(False),
            )
            .limit(1)
        )
    ).first()
    return row is not None


DOCUMENT_PROVIDER_CODES = {"po_public"}


def _is_document_provider(provider_code: str | None) -> bool:
    """Check whether document provider."""
    return bool(provider_code) and provider_code in DOCUMENT_PROVIDER_CODES


@dataclass(slots=True)
class DocumentValidationOutcome:
    """Represents document validation outcome."""

    payment: Payment
    validation: PaymentValidation


async def _get_or_create_status(session: AsyncSession, *, name: str) -> PaymentStatus:
    """Get or create status."""
    status = await crud_payment_status.get_by_name(session, name=name)
    if status is not None:
        return status

    return await crud_payment_status.create_draft(
        session=session,
        data=PaymentStatusCreate(
            name=name,
            description=f"Auto-created for document payment workflow: {name}",
        ),
        user=None,
    )


def _build_event_payload(
    *,
    payment: Payment,
    action: str,
    admin_user_id: uuid.UUID | None,
    reason: str | None,
    attachment_id: uuid.UUID | None,
    extra_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build event payload."""
    return {
        "payment_id": str(payment.id),
        "order_id": str(payment.order_id) if payment.order_id else None,
        "user_id": str(payment.user_id),
        "provider_code": payment.provider_code,
        "provider_reference": payment.provider_reference,
        "action": action,
        "admin_user_id": str(admin_user_id) if admin_user_id else None,
        "reason": reason,
        "attachment_id": str(attachment_id) if attachment_id else None,
        "metadata": extra_data,
    }


async def register_intent(
    session: AsyncSession,
    *,
    payment: Payment,
    instructions: str | None,
    user: User | None,
) -> Payment:
    """Execute register intent."""
    status = await _get_or_create_status(
        session, name=DOCUMENT_STATUS_DOCUMENT_REQUIRED
    )
    payment.payment_status_id = status.id
    session.add(payment)

    await crud_payment_validation.create_draft(
        session=session,
        data=PaymentValidationCreate(
            payment_id=payment.id,
            action=ACTION_REGISTER_INTENT,
            reason=instructions,
        ),
        user=user,
    )

    await outbox_registry.publish(
        session=session,
        event_type=EVENT_DOCUMENT_REQUIRED,
        payload=_build_event_payload(
            payment=payment,
            action=ACTION_REGISTER_INTENT,
            admin_user_id=None,
            reason=instructions,
            attachment_id=None,
            extra_data=None,
        ),
        correlation_id=payment.id,
    )

    return payment


async def mark_document_uploaded(
    session: AsyncSession,
    *,
    payment: Payment,
    attachment: PaymentAttachment,
    user: User | None,
) -> Payment:
    """Execute mark document uploaded."""
    if not _is_document_provider(payment.provider_code):
        raise PaymentNotDocumentValidatedError(
            f"Payment {payment.id} provider '{payment.provider_code}' is not document-validated"
        )

    status = await _get_or_create_status(
        session, name=DOCUMENT_STATUS_DOCUMENT_UPLOADED
    )
    payment.payment_status_id = status.id
    session.add(payment)

    await crud_payment_validation.create_draft(
        session=session,
        data=PaymentValidationCreate(
            payment_id=payment.id,
            action=ACTION_ATTACH_DOCUMENT,
            reason=None,
            extra_data={
                "attachment_id": str(attachment.id),
                "file_key": attachment.file_key,
                "filename": attachment.filename,
            },
        ),
        user=user,
    )

    await outbox_registry.publish(
        session=session,
        event_type=EVENT_DOCUMENT_UPLOADED,
        payload=_build_event_payload(
            payment=payment,
            action=ACTION_ATTACH_DOCUMENT,
            admin_user_id=None,
            reason=None,
            attachment_id=attachment.id,
            extra_data={
                "file_key": attachment.file_key,
                "filename": attachment.filename,
                "mimetype": attachment.mimetype,
            },
        ),
        correlation_id=payment.id,
    )

    return payment


async def approve_document_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    admin: User,
    comment: str | None,
) -> DocumentValidationOutcome:
    """Approve a document payment (purchase order): the same capture as a
    manual payment. Refused while no usable document is attached — the
    document is what the admin validates."""
    if not _is_document_provider(payment.provider_code):
        raise PaymentNotDocumentValidatedError(
            f"Payment {payment.id} provider '{payment.provider_code}' is not document-validated"
        )
    if not await has_usable_document(session, payment.id):
        raise PaymentDocumentMissingError(
            f"Payment {payment.id} has no uploaded document to approve"
        )

    status = await _get_or_create_status(session, name=DOCUMENT_STATUS_APPROVED)
    payment.payment_status_id = status.id
    session.add(payment)

    validation = await crud_payment_validation.create_draft(
        session=session,
        data=PaymentValidationCreate(
            payment_id=payment.id,
            action=ACTION_APPROVE,
            admin_user_id=admin.id,
            reason=comment,
        ),
        user=admin,
    )

    await outbox_registry.publish(
        session=session,
        event_type=EVENT_DOCUMENT_APPROVED,
        payload=_build_event_payload(
            payment=payment,
            action=ACTION_APPROVE,
            admin_user_id=admin.id,
            reason=comment,
            attachment_id=None,
            extra_data=None,
        ),
        correlation_id=payment.id,
    )

    return DocumentValidationOutcome(payment=payment, validation=validation)


async def reject_document_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    admin: User,
    reason: str,
) -> DocumentValidationOutcome:
    """Execute reject document payment."""
    if not _is_document_provider(payment.provider_code):
        raise PaymentNotDocumentValidatedError(
            f"Payment {payment.id} provider '{payment.provider_code}' is not document-validated"
        )

    status = await _get_or_create_status(session, name=DOCUMENT_STATUS_REJECTED)
    payment.payment_status_id = status.id
    session.add(payment)

    validation = await crud_payment_validation.create_draft(
        session=session,
        data=PaymentValidationCreate(
            payment_id=payment.id,
            action=ACTION_REJECT,
            admin_user_id=admin.id,
            reason=reason,
        ),
        user=admin,
    )

    await outbox_registry.publish(
        session=session,
        event_type=EVENT_DOCUMENT_REJECTED,
        payload=_build_event_payload(
            payment=payment,
            action=ACTION_REJECT,
            admin_user_id=admin.id,
            reason=reason,
            attachment_id=None,
            extra_data=None,
        ),
        correlation_id=payment.id,
    )

    return DocumentValidationOutcome(payment=payment, validation=validation)


async def mark_document_infected(
    session: AsyncSession,
    *,
    payment: Payment,
    attachment: PaymentAttachment,
    signature: str | None,
) -> Payment:
    """Execute mark document infected."""
    status = await _get_or_create_status(session, name=DOCUMENT_STATUS_REJECTED)
    payment.payment_status_id = status.id
    session.add(payment)

    await crud_payment_validation.create_draft(
        session=session,
        data=PaymentValidationCreate(
            payment_id=payment.id,
            action="document_infected",
            reason=f"Antivirus detected: {signature or 'unknown'}",
            extra_data={
                "attachment_id": str(attachment.id),
                "file_key": attachment.file_key,
                "signature": signature,
            },
        ),
        user=None,
    )

    await outbox_registry.publish(
        session=session,
        event_type=EVENT_DOCUMENT_INFECTED,
        payload=_build_event_payload(
            payment=payment,
            action="document_infected",
            admin_user_id=None,
            reason=signature,
            attachment_id=attachment.id,
            extra_data={"signature": signature},
        ),
        correlation_id=payment.id,
    )

    return payment
