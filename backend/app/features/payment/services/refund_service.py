"""Refund orchestration: validate, dispatch to the provider, record, notify.

Exposed flow (``refund_payment``):
1. Compute the refundable balance (payment amount − already-refunded non-failed).
2. Reject an amount that is ≤ 0 or exceeds the balance.
3. Ask the provider to refund (manual/PO → immediate ``completed``; PayZen →
   ``pending`` to finalise in the back office).
4. Persist a ``Refund`` row + a ``PaymentValidation`` audit entry.
5. When completed, set the payment status (Refunded / PartiallyRefunded) and
   publish ``payment.refunded`` (→ order status sync + customer email handlers).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.crud.refund import crud_refund
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_validation import PaymentValidation
from app.features.payment.models.refund import Refund
from app.features.payment.providers import get_provider
from app.features.payment.providers.base import PaymentProviderError
from app.features.payment.services.store_credit import SETTLED_PAYMENT_STATUSES
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry

PAYMENT_STATUS_REFUNDED = "Refunded"
PAYMENT_STATUS_PARTIALLY_REFUNDED = "PartiallyRefunded"
EVENT_PAYMENT_REFUNDED = "payment.refunded"


@dataclass(slots=True)
class RefundOutcome:
    """Result of a refund request returned to the API layer."""

    refund: Refund
    fully_refunded: bool
    message: str | None


async def _order_net_collected(session: AsyncSession, order_id: uuid.UUID) -> Decimal:
    """Σ of the order's settled payments − Σ of its completed refunds."""
    rows = await crud_payment.list_with_status_by_order_id(session, order_id=order_id)
    collected = sum(
        (Decimal(p.amount) for p, s in rows if s in SETTLED_PAYMENT_STATUSES),
        Decimal(0),
    )
    refunded = (
        await session.exec(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                col(Refund.order_id) == order_id,
                col(Refund.status) == "completed",
            )
        )
    ).one()
    return collected - Decimal(refunded)


async def refund_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    admin: User,
    amount: Decimal | None = None,
    reason: str | None = None,
) -> RefundOutcome:
    """Refund a captured payment (full when ``amount`` is omitted)."""
    # Capture before any commit (expires the ORM instances) -------------------
    payment_total = payment.amount
    payment_id = payment.id
    order_id = payment.order_id
    user_id = payment.user_id
    currency = payment.currency
    provider_code = payment.provider_code
    provider_reference = payment.provider_reference
    provider_data = dict(payment.provider_data or {})
    admin_id = admin.id

    already_refunded = await crud_refund.get_total_refunded(
        session, payment_id=payment_id
    )
    refundable = payment_total - already_refunded
    refund_amount = amount if amount is not None else refundable

    if refund_amount <= 0:
        raise AppError(
            code="refund.invalid_amount",
            status_code=400,
            message="Le montant du remboursement doit être positif.",
            details={"refundable": str(refundable)},
        )
    if refund_amount > refundable:
        raise AppError(
            code="refund.exceeds_refundable",
            status_code=400,
            message="Le remboursement dépasse le montant remboursable.",
            details={"requested": str(refund_amount), "refundable": str(refundable)},
        )

    try:
        provider = get_provider(provider_code)
    except PaymentProviderError as exc:
        raise AppError(
            code="refund.provider_unknown",
            status_code=400,
            message=f"Fournisseur de paiement inconnu : {provider_code}",
            details={"provider_code": provider_code},
        ) from exc

    try:
        result = await provider.refund(
            payment_reference=provider.refund_reference(
                provider_data=provider_data,
                provider_reference=provider_reference,
                fallback=str(order_id or payment_id),
            ),
            amount=refund_amount,
            currency=currency,
            reason=reason,
        )
    except PaymentProviderError as exc:
        raise AppError(
            code="refund.provider_failed",
            status_code=502,
            message=f"Le prestataire n'a pas pu rembourser : {exc}",
            details={"payment_id": str(payment_id)},
        ) from exc
    completed = result.status == "completed"
    now = datetime.now(UTC)

    refund = Refund(
        payment_id=payment_id,
        order_id=order_id,
        amount=refund_amount,
        currency=currency,
        reason=reason,
        status=result.status,
        provider_reference=result.provider_reference,
        processed_at=now if completed else None,
        created_by_id=admin_id,
    )
    session.add(refund)

    session.add(
        PaymentValidation(
            payment_id=payment_id,
            action="refund",
            admin_user_id=admin_id,
            reason=reason,
            extra_data={
                "amount": str(refund_amount),
                "currency": currency,
                "status": result.status,
                "message": result.message,
            },
        )
    )

    fully_refunded = False
    order_fully_refunded = False
    if completed:
        fully_refunded = (already_refunded + refund_amount) >= payment_total
        order_fully_refunded = fully_refunded
        if order_id is not None:
            # An order settled by several payments (deposit + balance, avoir +
            # cash…) is only « remboursée » when nothing it collected is left.
            await session.flush()
            order_fully_refunded = await _order_net_collected(session, order_id) <= 0
        status_name = (
            PAYMENT_STATUS_REFUNDED
            if fully_refunded
            else PAYMENT_STATUS_PARTIALLY_REFUNDED
        )
        status = await crud_payment_status.get_by_name(session, name=status_name)
        if status is not None:
            payment.payment_status_id = status.id
            session.add(payment)

        await outbox_registry.publish(
            session=session,
            event_type=EVENT_PAYMENT_REFUNDED,
            payload={
                # The credit note keys its idempotency on this: the outbox
                # delivers at least once, and two credit notes for one refund
                # would each burn a number in a gap-free legal sequence.
                "refund_id": str(refund.id),
                "payment_id": str(payment_id),
                "order_id": str(order_id) if order_id else None,
                "user_id": str(user_id),
                "amount": str(refund_amount),
                "currency": currency,
                "reason": reason,
                # Order-level: drives the order status, the stock release and
                # the wording of the customer e-mail.
                "fully_refunded": order_fully_refunded,
                "payment_fully_refunded": fully_refunded,
                "provider_code": provider_code,
            },
            correlation_id=payment_id,
        )

    await session.commit()
    await session.refresh(refund)
    return RefundOutcome(
        refund=refund, fully_refunded=fully_refunded, message=result.message
    )
