from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.crud.payment_validation import crud_payment_validation
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
)
from app.features.payment.models.payment_validation import (
    PaymentValidation,
    PaymentValidationCreate,
)
from app.features.payment.providers.manual import (
    MANUAL_STATUS_AWAITING_VALIDATION,
    MANUAL_STATUS_COMPLETED,
    MANUAL_STATUS_FAILED,
)
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry

EVENT_AWAITING_VALIDATION = "payment.awaiting_validation"
EVENT_CAPTURED = "payment.captured"
EVENT_REJECTED = "payment.rejected"

ACTION_REGISTER_INTENT = "register_intent"
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"


class PaymentNotManualError(RuntimeError):
    """Raised when a payment does not belong to a manual provider."""


@dataclass(slots=True)
class ManualValidationOutcome:
    """Represents manual validation outcome."""

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
            description=f"Auto-created for manual payment workflow: {name}",
        ),
        user=None,
    )


def _build_event_payload(
    *,
    payment: Payment,
    action: str,
    admin_user_id: uuid.UUID | None,
    reason: str | None,
    reference: str | None,
    extra_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build event payload."""
    return {
        "payment_id": str(payment.id),
        "order_id": str(payment.order_id) if payment.order_id else None,
        "user_id": str(payment.user_id),
        "provider_code": payment.provider_code,
        "provider_reference": payment.provider_reference,
        # The customer e-mail shows the amount received.
        "total_amount": str(payment.amount),
        "currency": payment.currency,
        "action": action,
        "admin_user_id": str(admin_user_id) if admin_user_id else None,
        "reason": reason,
        "reference": reference,
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
    awaiting_status = await _get_or_create_status(
        session,
        name=MANUAL_STATUS_AWAITING_VALIDATION,
    )
    payment.payment_status_id = awaiting_status.id
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
        event_type=EVENT_AWAITING_VALIDATION,
        payload=_build_event_payload(
            payment=payment,
            action=ACTION_REGISTER_INTENT,
            admin_user_id=None,
            reason=instructions,
            reference=None,
            extra_data=None,
        ),
        correlation_id=payment.id,
    )

    return payment


async def approve_manual_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    admin: User,
    reference: str | None,
    comment: str | None,
) -> ManualValidationOutcome:
    """Execute approve manual payment."""
    if not payment.provider_code or not payment.provider_code.startswith("manual_"):
        raise PaymentNotManualError(
            f"Payment {payment.id} provider '{payment.provider_code}' is not manual"
        )

    completed_status = await _get_or_create_status(
        session,
        name=MANUAL_STATUS_COMPLETED,
    )
    payment.payment_status_id = completed_status.id
    if reference is not None:
        payment.provider_reference = reference
    session.add(payment)

    extra_data: dict[str, Any] = {}
    if reference is not None:
        extra_data["reference"] = reference

    validation = await crud_payment_validation.create_draft(
        session=session,
        data=PaymentValidationCreate(
            payment_id=payment.id,
            action=ACTION_APPROVE,
            admin_user_id=admin.id,
            reason=comment,
            extra_data=extra_data or None,
        ),
        user=admin,
    )

    await outbox_registry.publish(
        session=session,
        event_type=EVENT_CAPTURED,
        payload=_build_event_payload(
            payment=payment,
            action=ACTION_APPROVE,
            admin_user_id=admin.id,
            reason=comment,
            reference=reference,
            extra_data=extra_data or None,
        ),
        correlation_id=payment.id,
    )

    return ManualValidationOutcome(payment=payment, validation=validation)


async def reject_manual_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    admin: User,
    reason: str,
) -> ManualValidationOutcome:
    """Execute reject manual payment."""
    if not payment.provider_code or not payment.provider_code.startswith("manual_"):
        raise PaymentNotManualError(
            f"Payment {payment.id} provider '{payment.provider_code}' is not manual"
        )

    failed_status = await _get_or_create_status(
        session,
        name=MANUAL_STATUS_FAILED,
    )
    payment.payment_status_id = failed_status.id
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
        event_type=EVENT_REJECTED,
        payload=_build_event_payload(
            payment=payment,
            action=ACTION_REJECT,
            admin_user_id=admin.id,
            reason=reason,
            reference=None,
            extra_data=None,
        ),
        correlation_id=payment.id,
    )

    return ManualValidationOutcome(payment=payment, validation=validation)
