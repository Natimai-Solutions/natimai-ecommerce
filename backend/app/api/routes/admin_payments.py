from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlmodel import col, func, or_, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.attachment.service import issue_download_url
from app.features.base.crud import RecordNotFoundError
from app.features.order.models.order import Order
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_attachment import crud_payment_attachment
from app.features.payment.crud.payment_validation import crud_payment_validation
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_attachment import (
    PaymentAttachmentPublic,
)
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.models.payment_receipt import (
    PaymentReceipt,
    PaymentReceiptPublic,
)
from app.features.payment.models.payment_status import PaymentStatus
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
    reject_manual_payment,
)
from app.features.payment.services.pending_validation import (
    pending_validation_conditions,
)
from app.features.payment.services.receipts import (
    ReceiptOutcome,
    cancel_receipt,
    received_amount,
    received_by_payment,
    record_receipt,
    settle_remaining,
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
    order_number: str | None = None
    is_document: bool = False
    #: Σ of the instalments already received on this payment (R3-P2).
    received_amount: float = 0


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


class PaymentListItem(BaseModel):
    """One row of the general payments list (A19)."""

    payment_id: uuid.UUID
    created_at: datetime | None = None
    provider_code: str
    provider_reference: str | None = None
    amount: float
    currency: str
    status: str | None = None
    method_name: str | None = None
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    order_id: uuid.UUID | None = None
    order_number: str | None = None
    is_document: bool = False
    received_amount: float = 0


class PaymentListResponse(BaseModel):
    """A page of payments, the total and the filter values in use."""

    data: list[PaymentListItem] = Field(default_factory=list)
    count: int = 0
    statuses: list[str] = Field(default_factory=list)
    provider_codes: list[str] = Field(default_factory=list)


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    session: SessionDep,
    _admin: CurrentSuperUser,
    q: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=50),
    provider_code: str | None = Query(default=None, max_length=50),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaymentListResponse:
    """Every payment, newest first, with its status, method, customer and order (A19).

    ``q`` searches the order number, the provider reference and the customer's
    name or e-mail; ``status`` and ``provider_code`` filter exactly; the dates
    bound the creation day (inclusive). The validation screen keeps its own
    narrower list (``/pending-validation``): this one is the ledger.
    """
    joins = (
        select(Payment, PaymentStatus.name, User, Order.order_number)
        .outerjoin(
            PaymentStatus, col(PaymentStatus.id) == col(Payment.payment_status_id)
        )
        .outerjoin(User, col(User.id) == col(Payment.user_id))
        .outerjoin(Order, col(Order.id) == col(Payment.order_id))
    )
    conditions: list[Any] = [col(Payment.is_active).is_(True)]
    if status:
        conditions.append(col(PaymentStatus.name) == status)
    if provider_code:
        conditions.append(col(Payment.provider_code) == provider_code)
    if date_from:
        conditions.append(
            col(Payment.created_at) >= datetime.combine(date_from, time.min, tzinfo=UTC)
        )
    if date_to:
        conditions.append(
            col(Payment.created_at)
            < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        )
    if q and q.strip():
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                col(Order.order_number).ilike(like),
                col(Payment.provider_reference).ilike(like),
                col(User.email).ilike(like),
                col(User.full_name).ilike(like),
            )
        )
    count_statement = (
        select(func.count())
        .select_from(Payment)
        .outerjoin(
            PaymentStatus, col(PaymentStatus.id) == col(Payment.payment_status_id)
        )
        .outerjoin(User, col(User.id) == col(Payment.user_id))
        .outerjoin(Order, col(Order.id) == col(Payment.order_id))
        .where(*conditions)
    )
    count = int((await session.exec(count_statement)).one())
    rows = (
        await session.exec(
            joins.where(*conditions)
            .order_by(col(Payment.created_at).desc().nulls_last(), col(Payment.id))
            .offset(skip)
            .limit(limit)
        )
    ).all()
    received = await received_by_payment(session, [row[0].id for row in rows])
    method_ids = {row[0].payment_method_id for row in rows if row[0].payment_method_id}
    method_names: dict[uuid.UUID, str | None] = {}
    if method_ids:
        method_names = dict(
            (
                await session.exec(
                    select(PaymentMethod.id, PaymentMethod.name).where(
                        col(PaymentMethod.id).in_(method_ids)
                    )
                )
            ).all()
        )
    items = [
        PaymentListItem(
            payment_id=payment.id,
            created_at=payment.created_at,
            provider_code=payment.provider_code,
            provider_reference=payment.provider_reference,
            amount=float(payment.amount),
            currency=payment.currency,
            status=status_name,
            method_name=(
                method_names.get(payment.payment_method_id)
                if payment.payment_method_id
                else None
            ),
            user_id=payment.user_id,
            user_name=user.full_name if user else None,
            user_email=user.email if user else None,
            order_id=payment.order_id,
            order_number=order_number,
            is_document=payment.provider_code in DOCUMENT_PROVIDER_CODES,
            received_amount=float(received.get(payment.id, 0)),
        )
        for payment, status_name, user, order_number in rows
    ]
    statuses = list(
        (
            await session.exec(
                select(PaymentStatus.name).order_by(col(PaymentStatus.name))
            )
        ).all()
    )
    provider_codes = list(
        (
            await session.exec(
                select(Payment.provider_code)
                .distinct()
                .order_by(col(Payment.provider_code))
            )
        ).all()
    )
    return PaymentListResponse(
        data=items, count=count, statuses=statuses, provider_codes=provider_codes
    )


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

    # And the order numbers (CMD-…) the admin recognises, in one more query.
    order_ids = {p.order_id for p in payments if p.order_id is not None}
    numbers_by_order: dict[uuid.UUID, str | None] = {}
    if order_ids:
        order_result = await session.exec(
            select(Order.id, Order.order_number).where(col(Order.id).in_(order_ids))
        )
        numbers_by_order = dict(order_result.all())

    received = await received_by_payment(session, [p.id for p in payments])

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
                order_number=numbers_by_order.get(p.order_id) if p.order_id else None,
                is_document=p.provider_code in DOCUMENT_PROVIDER_CODES,
                received_amount=float(received.get(p.id, 0)),
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
        if not (payment.provider_code or "").startswith("manual_"):
            await session.rollback()
            raise AppError(
                code="payment.not_manual",
                status_code=400,
                message=f"Payment {payment.id} provider '{payment.provider_code}' is not manual",
                details={
                    "payment_id": str(payment_id),
                    "provider_code": payment.provider_code,
                },
            )
        try:
            # What is left to receive becomes one receipt, which settles the
            # payment: the history of every amount received stays complete.
            outcome = await settle_remaining(
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
        if await received_amount(session, payment_id=payment.id) > 0:
            await session.rollback()
            raise AppError(
                code="payment.receipt.exists",
                status_code=409,
                message=(
                    "Des versements ont déjà été reçus sur ce paiement : "
                    "annulez-les d'abord (chèque impayé, somme rendue)"
                ),
                details={"payment_id": str(payment_id)},
            )
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


# ---------------------------------------------------------------------------
# Receipts: instalments received on a manual payment (R3-P2)
# ---------------------------------------------------------------------------


class ReceiptCreate(BaseModel):
    """An amount received against a pending manual payment."""

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    received_at: datetime | None = Field(
        default=None, description="When the money was received (default: now)"
    )
    method: str | None = Field(
        default=None,
        description="cash | check | transfer | card | other (default: the payment's)",
    )
    reference: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class ReceiptCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReceiptResult(BaseModel):
    """A recorded receipt and where its payment stands."""

    receipt: PaymentReceiptPublic
    payment_id: uuid.UUID
    received_amount: Decimal
    remaining_amount: Decimal
    payment_settled: bool


def receipt_result(outcome: ReceiptOutcome) -> ReceiptResult:
    return ReceiptResult(
        receipt=PaymentReceiptPublic.model_validate(
            outcome.receipt, from_attributes=True
        ),
        payment_id=outcome.payment.id,
        received_amount=outcome.received,
        remaining_amount=outcome.remaining,
        payment_settled=outcome.settled is not None,
    )


@router.get("/{payment_id}/receipts", response_model=list[PaymentReceiptPublic])
async def list_payment_receipts(
    payment_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[PaymentReceiptPublic]:
    """Every receipt of a payment, cancelled ones included, oldest first."""
    await _get_payment_or_404(session, payment_id)
    rows = await session.exec(
        select(PaymentReceipt)
        .where(col(PaymentReceipt.payment_id) == payment_id)
        .order_by(col(PaymentReceipt.received_at))
    )
    return [
        PaymentReceiptPublic.model_validate(r, from_attributes=True) for r in rows.all()
    ]


@router.post("/{payment_id}/receipts", response_model=ReceiptResult)
async def create_payment_receipt(
    payment_id: uuid.UUID,
    body: ReceiptCreate,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> ReceiptResult:
    """Record an instalment; the one that reaches the amount settles the payment."""
    payment = await _get_payment_or_404(session, payment_id)
    try:
        outcome = await record_receipt(
            session,
            payment=payment,
            admin=admin,
            amount=body.amount,
            received_at=body.received_at,
            method=body.method,
            reference=body.reference,
            note=body.note,
        )
        result = receipt_result(outcome)
        await session.commit()
    except AppError:
        await session.rollback()
        raise
    return result


@router.post("/receipts/{receipt_id}/cancel", response_model=PaymentReceiptPublic)
async def cancel_payment_receipt(
    receipt_id: uuid.UUID,
    body: ReceiptCancel,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> PaymentReceiptPublic:
    """Cancel an instalment of a still pending payment (bounced cheque…)."""
    receipt = await session.get(PaymentReceipt, receipt_id)
    if receipt is None:
        raise AppError(
            code="payment.receipt.not_found",
            status_code=404,
            message="Versement introuvable",
            details={"receipt_id": str(receipt_id)},
        )
    try:
        await cancel_receipt(session, receipt=receipt, admin=admin, reason=body.reason)
        public = PaymentReceiptPublic.model_validate(receipt, from_attributes=True)
        await session.commit()
    except AppError:
        await session.rollback()
        raise
    return public
