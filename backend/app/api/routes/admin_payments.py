from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.features.base.crud import RecordNotFoundError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.crud.payment_validation import crud_payment_validation
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_validation import (
    PaymentValidation,
    PaymentValidationPublic,
)
from app.features.payment.providers.manual import (
    MANUAL_STATUS_AWAITING_VALIDATION,
)
from app.features.payment.services.manual_payment import (
    PaymentNotManualError,
    approve_manual_payment,
    reject_manual_payment,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/payments", tags=["admin-payment"])


class PaymentApproveRequest(BaseModel):
    reference: str | None = Field(
        default=None,
        description="External reference confirming receipt (bank ref, check number, etc.)",
    )
    comment: str | None = Field(
        default=None,
        description="Optional comment recorded in the validation audit trail",
    )


class PaymentRejectRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Reason for rejection (mandatory for audit)",
    )


class PaymentPendingValidationItem(BaseModel):
    payment_id: uuid.UUID
    provider_code: str
    provider_reference: str | None
    amount: float
    currency: str
    user_id: uuid.UUID
    order_id: uuid.UUID | None


class PaymentValidationResponse(BaseModel):
    payment_id: uuid.UUID
    payment_status_id: uuid.UUID | None
    validation: PaymentValidationPublic


async def _get_payment_or_404(session: SessionDep, payment_id: uuid.UUID) -> Payment:
    try:
        return await crud_payment.read(session, id=payment_id)
    except RecordNotFoundError as e:
        raise HTTPException(404, f"Payment {payment_id} not found") from e


@router.get("/pending-validation", response_model=list[PaymentPendingValidationItem])
async def list_pending_validation(
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[PaymentPendingValidationItem]:
    awaiting_status = await crud_payment_status.get_by_name(
        session, name=MANUAL_STATUS_AWAITING_VALIDATION
    )
    if awaiting_status is None:
        return []

    statement = (
        select(Payment)
        .where(
            Payment.payment_status_id == awaiting_status.id,
            col(Payment.provider_code).startswith("manual_"),
            col(Payment.is_active).is_(True),
            col(Payment.is_admin_active).is_(True),
        )
        .order_by(col(Payment.created_at).desc())
    )
    result = await session.exec(statement)
    payments = list(result.all())

    return [
        PaymentPendingValidationItem(
            payment_id=p.id,
            provider_code=p.provider_code,
            provider_reference=p.provider_reference,
            amount=float(p.amount),
            currency=p.currency,
            user_id=p.user_id,
            order_id=p.order_id,
        )
        for p in payments
    ]


@router.get("/{payment_id}/validations", response_model=list[PaymentValidationPublic])
async def list_payment_validations(
    payment_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[PaymentValidation]:
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
    payment = await _get_payment_or_404(session, payment_id)

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
        raise HTTPException(400, str(e)) from e

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
    payment = await _get_payment_or_404(session, payment_id)

    try:
        outcome = await reject_manual_payment(
            session,
            payment=payment,
            admin=admin,
            reason=body.reason,
        )
    except PaymentNotManualError as e:
        await session.rollback()
        raise HTTPException(400, str(e)) from e

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
