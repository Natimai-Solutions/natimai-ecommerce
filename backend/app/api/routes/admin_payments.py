from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.attachment.service import issue_download_url
from app.features.base.crud import RecordNotFoundError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_attachment import crud_payment_attachment
from app.features.payment.crud.payment_validation import crud_payment_validation
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_attachment import (
    PaymentAttachmentPublic,
)
from app.features.payment.models.payment_validation import (
    PaymentValidation,
    PaymentValidationPublic,
)
from app.features.payment.models.refund import RefundPublic
from app.features.payment.services.capture_service import capture_payment
from app.features.payment.services.document_payment import (
    DOCUMENT_PROVIDER_CODES,
    DocumentValidationOutcome,
    PaymentNotDocumentValidatedError,
    approve_document_payment,
    reject_document_payment,
)
from app.features.payment.services.manual_payment import (
    ManualValidationOutcome,
    PaymentNotManualError,
    approve_manual_payment,
    reject_manual_payment,
)
from app.features.payment.services.pending_validation import (
    pending_validation_conditions,
)
from app.features.payment.services.refund_service import refund_payment
from app.features.user.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/payments", tags=["admin-payment"])


class PaymentApproveRequest(BaseModel):
    """Represents payment approve request."""

    reference: str | None = Field(
        default=None,
        description="External reference confirming receipt (bank ref, check number, etc.)",
    )
    comment: str | None = Field(
        default=None,
        description="Optional comment recorded in the validation audit trail",
    )


class PaymentRejectRequest(BaseModel):
    """Represents payment reject request."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Reason for rejection (mandatory for audit)",
    )


class PaymentPendingValidationItem(BaseModel):
    """Represents payment pending validation item."""

    payment_id: uuid.UUID
    provider_code: str
    provider_reference: str | None
    amount: float
    currency: str
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    order_id: uuid.UUID | None
    is_document: bool = False


class PaymentValidationResponse(BaseModel):
    """Represents payment validation response."""

    payment_id: uuid.UUID
    payment_status_id: uuid.UUID | None
    validation: PaymentValidationPublic


class PaymentRefundRequest(BaseModel):
    """Refund request: full when amount is omitted, partial otherwise."""

    amount: Decimal | None = Field(
        default=None,
        gt=0,
        description="Montant à rembourser ; total remboursable si omis",
    )
    reason: str | None = Field(default=None, max_length=1024)


class PaymentRefundResponse(BaseModel):
    """Represents payment refund response."""

    payment_id: uuid.UUID
    refund: RefundPublic
    fully_refunded: bool
    message: str | None = None


class PaymentCaptureResponse(BaseModel):
    """Represents payment capture response."""

    payment_id: uuid.UUID
    payment_status_id: uuid.UUID | None
    message: str | None = None


async def _get_payment_or_404(session: SessionDep, payment_id: uuid.UUID) -> Payment:
    """Get payment or 404."""
    try:
        return await crud_payment.read(session, id=payment_id)
    except RecordNotFoundError as e:
        raise AppError(
            code="payment.not_found",
            status_code=404,
            message=f"Payment {payment_id} not found",
            details={"payment_id": str(payment_id)},
        ) from e


@router.get("/pending-validation", response_model=list[PaymentPendingValidationItem])
async def list_pending_validation(
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[PaymentPendingValidationItem]:
    """List pending validation."""
    conditions = await pending_validation_conditions(session)
    if conditions is None:
        return []

    statement = (
        select(Payment).where(*conditions).order_by(col(Payment.created_at).desc())
    )
    result = await session.exec(statement)
    payments = list(result.all())

    # Resolve client display names in one query.
    user_ids = {p.user_id for p in payments}
    users_by_id: dict[uuid.UUID, User] = {}
    if user_ids:
        user_result = await session.exec(select(User).where(col(User.id).in_(user_ids)))
        users_by_id = {u.id: u for u in user_result.all()}

    items: list[PaymentPendingValidationItem] = []
    for p in payments:
        user = users_by_id.get(p.user_id)
        items.append(
            PaymentPendingValidationItem(
                payment_id=p.id,
                provider_code=p.provider_code,
                provider_reference=p.provider_reference,
                amount=float(p.amount),
                currency=p.currency,
                user_id=p.user_id,
                user_name=user.full_name if user else None,
                user_email=user.email if user else None,
                order_id=p.order_id,
                is_document=p.provider_code in DOCUMENT_PROVIDER_CODES,
            )
        )
    return items


@router.get("/{payment_id}/validations", response_model=list[PaymentValidationPublic])
async def list_payment_validations(
    payment_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[PaymentValidation]:
    """List payment validations."""
    await _get_payment_or_404(session, payment_id)
    return await crud_payment_validation.list_for_payment(
        session, payment_id=payment_id
    )


@router.post("/{payment_id}/approve", response_model=PaymentValidationResponse)
async def approve_payment(
    payment_id: uuid.UUID,
    body: PaymentApproveRequest,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> PaymentValidationResponse:
    """Execute approve payment."""
    payment = await _get_payment_or_404(session, payment_id)
    outcome: DocumentValidationOutcome | ManualValidationOutcome

    if payment.provider_code in DOCUMENT_PROVIDER_CODES:
        try:
            outcome = await approve_document_payment(
                session,
                payment=payment,
                admin=admin,
                comment=body.comment,
            )
        except PaymentNotDocumentValidatedError as e:
            await session.rollback()
            raise AppError(
                code="payment.not_document_validated",
                status_code=400,
                message=str(e),
                details={
                    "payment_id": str(payment_id),
                    "provider_code": payment.provider_code,
                },
            ) from e
    else:
        try:
            outcome = await approve_manual_payment(
                session,
                payment=payment,
                admin=admin,
                reference=body.reference,
                comment=body.comment,
            )
        except PaymentNotManualError as e:
            await session.rollback()
            raise AppError(
                code="payment.not_manual",
                status_code=400,
                message=str(e),
                details={
                    "payment_id": str(payment_id),
                    "provider_code": payment.provider_code,
                },
            ) from e

    await session.commit()
    await session.refresh(outcome.payment)
    await session.refresh(outcome.validation)

    return PaymentValidationResponse(
        payment_id=outcome.payment.id,
        payment_status_id=outcome.payment.payment_status_id,
        validation=PaymentValidationPublic.model_validate(
            outcome.validation, from_attributes=True
        ),
    )


@router.post("/{payment_id}/reject", response_model=PaymentValidationResponse)
async def reject_payment(
    payment_id: uuid.UUID,
    body: PaymentRejectRequest,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> PaymentValidationResponse:
    """Execute reject payment."""
    payment = await _get_payment_or_404(session, payment_id)
    outcome: DocumentValidationOutcome | ManualValidationOutcome

    if payment.provider_code in DOCUMENT_PROVIDER_CODES:
        try:
            outcome = await reject_document_payment(
                session,
                payment=payment,
                admin=admin,
                reason=body.reason,
            )
        except PaymentNotDocumentValidatedError as e:
            await session.rollback()
            raise AppError(
                code="payment.not_document_validated",
                status_code=400,
                message=str(e),
                details={
                    "payment_id": str(payment_id),
                    "provider_code": payment.provider_code,
                },
            ) from e
    else:
        try:
            outcome = await reject_manual_payment(
                session,
                payment=payment,
                admin=admin,
                reason=body.reason,
            )
        except PaymentNotManualError as e:
            await session.rollback()
            raise AppError(
                code="payment.not_manual",
                status_code=400,
                message=str(e),
                details={
                    "payment_id": str(payment_id),
                    "provider_code": payment.provider_code,
                },
            ) from e

    await session.commit()
    await session.refresh(outcome.payment)
    await session.refresh(outcome.validation)

    return PaymentValidationResponse(
        payment_id=outcome.payment.id,
        payment_status_id=outcome.payment.payment_status_id,
        validation=PaymentValidationPublic.model_validate(
            outcome.validation, from_attributes=True
        ),
    )


@router.post("/{payment_id}/refund", response_model=PaymentRefundResponse)
async def refund_payment_route(
    payment_id: uuid.UUID,
    body: PaymentRefundRequest,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> PaymentRefundResponse:
    """Refund a payment — full when ``amount`` is omitted, partial otherwise.

    Manual / purchase-order payments are refunded immediately; PayZen refunds are
    recorded as ``pending`` to finalise in the provider back office.
    """
    payment = await _get_payment_or_404(session, payment_id)
    outcome = await refund_payment(
        session=session,
        payment=payment,
        admin=admin,
        amount=body.amount,
        reason=body.reason,
    )
    return PaymentRefundResponse(
        payment_id=payment_id,
        refund=RefundPublic.model_validate(outcome.refund, from_attributes=True),
        fully_refunded=outcome.fully_refunded,
        message=outcome.message,
    )


@router.post("/{payment_id}/capture", response_model=PaymentCaptureResponse)
async def capture_payment_route(
    payment_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> PaymentCaptureResponse:
    """Capture an authorised card payment (deferred debit, e.g. at shipment)."""
    payment = await _get_payment_or_404(session, payment_id)
    outcome = await capture_payment(session=session, payment=payment, admin=admin)
    return PaymentCaptureResponse(
        payment_id=payment_id,
        payment_status_id=outcome.payment.payment_status_id,
        message=outcome.message,
    )


class AttachmentDownloadResponse(BaseModel):
    """Represents attachment download response."""

    download_url: str
    expires_in: int


@router.get(
    "/{payment_id}/attachments",
    response_model=list[PaymentAttachmentPublic],
)
async def list_payment_attachments(
    payment_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[PaymentAttachmentPublic]:
    """List payment attachments."""
    await _get_payment_or_404(session, payment_id)
    items = await crud_payment_attachment.list_for_payment(
        session, payment_id=payment_id
    )
    return [
        PaymentAttachmentPublic.model_validate(item, from_attributes=True)
        for item in items
    ]


@router.get(
    "/{payment_id}/attachments/{attachment_id}/download",
    response_model=AttachmentDownloadResponse,
)
async def get_attachment_download_url(
    payment_id: uuid.UUID,
    attachment_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> AttachmentDownloadResponse:
    """Get attachment download url."""
    await _get_payment_or_404(session, payment_id)

    try:
        attachment = await crud_payment_attachment.read(session, id=attachment_id)
    except RecordNotFoundError as e:
        raise AppError(
            code="internal.record_not_found",
            status_code=404,
            message=f"Attachment {attachment_id} not found",
            details={"attachment_id": str(attachment_id)},
        ) from e

    if attachment.payment_id != payment_id:
        raise AppError(
            code="internal.record_not_found",
            status_code=404,
            message="Attachment does not belong to this payment",
            details={
                "attachment_id": str(attachment_id),
                "payment_id": str(payment_id),
            },
        )

    if attachment.av_scanned and attachment.av_clean is False:
        raise AppError(
            code="attachment.validation_failed",
            status_code=403,
            message=f"Attachment quarantined by antivirus: {attachment.av_signature}",
            details={"reason": "quarantined"},
        )

    presigned = issue_download_url(
        file_key=attachment.file_key,
        filename=attachment.filename,
    )
    return AttachmentDownloadResponse(
        download_url=presigned.url,
        expires_in=presigned.expires_in,
    )
