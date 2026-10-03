"""Receipts against manual payments: instalments, counter payments, bounced
cheques (R3-P2).

A manual payment (cash, cheque, transfer) waits in ``AwaitingValidation``
until the shop has received its amount. Each amount received is recorded as a
:class:`PaymentReceipt`:

* while the receipts fall short, the payment stays pending and
  ``payment.partially_received`` moves the order to « partiellement payée »
  and tells the customer what is left;
* the receipt that reaches the amount settles the payment through the usual
  approval (``Completed`` + ``payment.captured``): order paid or deposit paid,
  stock confirmed, invoice, e-mail — nothing new downstream;
* a receipt can be cancelled while the payment is still pending (a bounced
  cheque, cash handed back): ``payment.receipt_cancelled`` recomputes the
  order status. Once the payment is settled, a bounced cheque is an
  accounting incident handled by a refund or a credit note, not here.

« Enregistrer un encaissement » on an order that has no pending manual payment
for the part due (the customer ordered by card, or the balance was never
initiated) creates that payment on the spot, then records the receipt.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_validation import crud_payment_validation
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.models.payment_receipt import (
    RECEIPT_METHODS,
    PaymentReceipt,
)
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.payment_validation import PaymentValidationCreate
from app.features.payment.models.refund import Refund
from app.features.payment.providers.manual import MANUAL_STATUS_AWAITING_VALIDATION
from app.features.payment.services.deposit import (
    next_payment_kind,
    remaining_amount,
)
from app.features.payment.services.manual_payment import (
    ManualValidationOutcome,
    _get_or_create_status,
    approve_manual_payment,
)
from app.features.payment.services.store_credit import (
    SETTLED_PAYMENT_STATUSES,
    settled_by_kind,
)
from app.outbox.registry import outbox_registry
from app.utils.money import quantize_amount

EVENT_PARTIALLY_RECEIVED = "payment.partially_received"
EVENT_RECEIPT_CANCELLED = "payment.receipt_cancelled"

ACTION_RECEIPT = "receipt"
ACTION_RECEIPT_CANCELLED = "receipt_cancelled"

#: Receipt method implied by a manual provider, and the reverse.
DEFAULT_METHOD_BY_PROVIDER: dict[str, str] = {
    "manual_cash": "cash",
    "manual_check": "check",
    "manual_transfer": "transfer",
}
PROVIDER_BY_METHOD: dict[str, str] = {
    method: provider for provider, method in DEFAULT_METHOD_BY_PROVIDER.items()
}

# A receipt dated in the future is a typo; allow a little clock skew.
_FUTURE_TOLERANCE = timedelta(minutes=10)

_ZERO = Decimal("0")


@dataclass(slots=True)
class ReceiptOutcome:
    """What recording a receipt did to its payment."""

    receipt: PaymentReceipt
    payment: Payment
    received: Decimal
    remaining: Decimal
    #: Set when this receipt settled the payment.
    settled: ManualValidationOutcome | None = None


def _now() -> datetime:
    return datetime.now(UTC)


async def active_receipts(
    session: AsyncSession, *, payment_id: uuid.UUID
) -> list[PaymentReceipt]:
    rows = await session.exec(
        select(PaymentReceipt)
        .where(
            col(PaymentReceipt.payment_id) == payment_id,
            col(PaymentReceipt.is_active).is_(True),
        )
        .order_by(col(PaymentReceipt.received_at))
    )
    return list(rows.all())


async def received_by_payment(
    session: AsyncSession, payment_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    """Σ of the active receipts of each payment, in one query."""
    ids = list(payment_ids)
    if not ids:
        return {}
    rows = await session.exec(
        select(PaymentReceipt.payment_id, func.sum(PaymentReceipt.amount))
        .where(
            col(PaymentReceipt.payment_id).in_(ids),
            col(PaymentReceipt.is_active).is_(True),
        )
        .group_by(col(PaymentReceipt.payment_id))
    )
    return {payment_id: Decimal(total) for payment_id, total in rows.all()}


async def received_amount(session: AsyncSession, *, payment_id: uuid.UUID) -> Decimal:
    return (await received_by_payment(session, [payment_id])).get(payment_id, _ZERO)


async def _status_name(session: AsyncSession, payment: Payment) -> str | None:
    if payment.payment_status_id is None:
        return None
    status = await session.get(PaymentStatus, payment.payment_status_id)
    return status.name if status is not None else None


def _check_method(method: str) -> str:
    normalized = method.strip().lower()
    if normalized not in RECEIPT_METHODS:
        raise AppError(
            code="payment.receipt.method_invalid",
            status_code=400,
            message=f"Mode d'encaissement inconnu : {method!r}",
            details={"allowed": list(RECEIPT_METHODS)},
        )
    return normalized


def _check_received_at(received_at: datetime | None) -> datetime:
    if received_at is None:
        return _now()
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    if received_at > _now() + _FUTURE_TOLERANCE:
        raise AppError(
            code="payment.receipt.date_in_future",
            status_code=400,
            message="La date de réception ne peut pas être dans le futur",
            details={},
        )
    return received_at


async def _assert_pending_manual(session: AsyncSession, payment: Payment) -> None:
    if not (payment.provider_code or "").startswith("manual_"):
        raise AppError(
            code="payment.receipt.not_manual",
            status_code=400,
            message="Seul un paiement manuel (espèces, chèque, virement) reçoit des versements",
            details={
                "payment_id": str(payment.id),
                "provider_code": payment.provider_code,
            },
        )
    status_name = await _status_name(session, payment)
    if status_name != MANUAL_STATUS_AWAITING_VALIDATION:
        raise AppError(
            code="payment.receipt.not_pending",
            status_code=409,
            message="Ce paiement n'attend plus de versement",
            details={"payment_id": str(payment.id), "payment_status": status_name},
        )


def _event_payload(
    payment: Payment,
    *,
    receipt: PaymentReceipt,
    received: Decimal,
    remaining: Decimal,
) -> dict[str, Any]:
    return {
        "payment_id": str(payment.id),
        "order_id": str(payment.order_id) if payment.order_id else None,
        "user_id": str(payment.user_id),
        "provider_code": payment.provider_code,
        "kind": payment.kind,
        "receipt_id": str(receipt.id),
        "amount": str(receipt.amount),
        "received_amount": str(received),
        "remaining_amount": str(remaining),
        "total_amount": str(payment.amount),
        "currency": payment.currency,
        "method": receipt.method,
    }


async def record_receipt(
    session: AsyncSession,
    *,
    payment: Payment,
    admin: Any,
    amount: Decimal,
    received_at: datetime | None = None,
    method: str | None = None,
    reference: str | None = None,
    note: str | None = None,
) -> ReceiptOutcome:
    """Record an amount received against a pending manual payment; settle the
    payment when the receipts reach its amount. Flushes, no commit."""
    await _assert_pending_manual(session, payment)
    currency = payment.currency or "XPF"
    amount = quantize_amount(Decimal(amount), currency)
    if amount <= 0:
        raise AppError(
            code="payment.receipt.amount_invalid",
            status_code=400,
            message="Le montant reçu doit être positif",
            details={},
        )
    already = await received_amount(session, payment_id=payment.id)
    remaining_before = Decimal(payment.amount) - already
    if amount > remaining_before:
        raise AppError(
            code="payment.receipt.exceeds_amount",
            status_code=400,
            message=(
                f"Le versement dépasse le reste dû ({remaining_before} {currency})"
            ),
            details={"remaining_amount": str(remaining_before)},
        )

    receipt = PaymentReceipt(
        payment_id=payment.id,
        order_id=payment.order_id,
        amount=amount,
        currency=currency,
        received_at=_check_received_at(received_at),
        method=_check_method(
            method or DEFAULT_METHOD_BY_PROVIDER.get(payment.provider_code, "other")
        ),
        reference=(reference or "").strip() or None,
        note=(note or "").strip() or None,
        recorded_by_id=getattr(admin, "id", None),
        created_at=_now(),
        created_by_id=getattr(admin, "id", None),
    )
    session.add(receipt)
    await session.flush()

    received = already + amount
    remaining = Decimal(payment.amount) - received
    if remaining == 0:
        settled = await approve_manual_payment(
            session,
            payment=payment,
            admin=admin,
            reference=receipt.reference,
            comment=receipt.note,
        )
        return ReceiptOutcome(
            receipt=receipt,
            payment=payment,
            received=received,
            remaining=remaining,
            settled=settled,
        )

    await crud_payment_validation.create_draft(
        session=session,
        data=PaymentValidationCreate(
            payment_id=payment.id,
            action=ACTION_RECEIPT,
            admin_user_id=getattr(admin, "id", None),
            reason=receipt.note,
            extra_data={
                "receipt_id": str(receipt.id),
                "amount": str(amount),
                "received_amount": str(received),
                "remaining_amount": str(remaining),
                "method": receipt.method,
                "reference": receipt.reference,
            },
        ),
        user=admin,
    )
    await outbox_registry.publish(
        session=session,
        event_type=EVENT_PARTIALLY_RECEIVED,
        payload=_event_payload(
            payment, receipt=receipt, received=received, remaining=remaining
        ),
        correlation_id=payment.id,
    )
    return ReceiptOutcome(
        receipt=receipt, payment=payment, received=received, remaining=remaining
    )


async def settle_remaining(
    session: AsyncSession,
    *,
    payment: Payment,
    admin: Any,
    reference: str | None,
    comment: str | None,
) -> ManualValidationOutcome:
    """« Approuver » a manual payment: record what is left to receive as one
    receipt, which settles it. Flushes, no commit."""
    await _assert_pending_manual(session, payment)
    already = await received_amount(session, payment_id=payment.id)
    outcome = await record_receipt(
        session,
        payment=payment,
        admin=admin,
        amount=Decimal(payment.amount) - already,
        reference=reference,
        note=comment,
    )
    assert outcome.settled is not None  # the whole remainder was recorded
    return outcome.settled


async def cancel_receipt(
    session: AsyncSession,
    *,
    receipt: PaymentReceipt,
    admin: Any,
    reason: str,
) -> Decimal:
    """Cancel a receipt of a still pending payment (bounced cheque, cash handed
    back). Returns what is still received on the payment. Flushes, no commit."""
    if not receipt.is_active:
        raise AppError(
            code="payment.receipt.already_cancelled",
            status_code=409,
            message="Ce versement est déjà annulé",
            details={"receipt_id": str(receipt.id)},
        )
    reason = reason.strip()
    if not reason:
        raise AppError(
            code="payment.receipt.reason_required",
            status_code=400,
            message="Indiquez le motif de l'annulation (chèque impayé, remboursé…)",
            details={},
        )
    payment = await session.get(Payment, receipt.payment_id)
    if payment is None:
        raise AppError(
            code="payment.not_found",
            status_code=404,
            message="Paiement introuvable",
            details={"payment_id": str(receipt.payment_id)},
        )
    if await _status_name(session, payment) != MANUAL_STATUS_AWAITING_VALIDATION:
        raise AppError(
            code="payment.receipt.payment_settled",
            status_code=409,
            message=(
                "Le paiement est déjà soldé : un chèque impayé après encaissement "
                "se traite par un remboursement ou un avoir"
            ),
            details={"payment_id": str(payment.id)},
        )

    receipt.is_active = False
    receipt.cancelled_at = _now()
    receipt.cancelled_by_id = getattr(admin, "id", None)
    receipt.cancel_reason = reason[:500]
    receipt.modify_at = receipt.cancelled_at
    receipt.modify_by_id = receipt.cancelled_by_id
    session.add(receipt)
    await session.flush()

    received = await received_amount(session, payment_id=payment.id)
    remaining = Decimal(payment.amount) - received
    await crud_payment_validation.create_draft(
        session=session,
        data=PaymentValidationCreate(
            payment_id=payment.id,
            action=ACTION_RECEIPT_CANCELLED,
            admin_user_id=getattr(admin, "id", None),
            reason=receipt.cancel_reason,
            extra_data={
                "receipt_id": str(receipt.id),
                "amount": str(receipt.amount),
                "received_amount": str(received),
            },
        ),
        user=admin,
    )
    await outbox_registry.publish(
        session=session,
        event_type=EVENT_RECEIPT_CANCELLED,
        payload=_event_payload(
            payment, receipt=receipt, received=received, remaining=remaining
        ),
        correlation_id=payment.id,
    )
    return received


async def record_counter_payment(
    session: AsyncSession,
    *,
    order: Any,
    admin: Any,
    amount: Decimal,
    method: str,
    received_at: datetime | None = None,
    reference: str | None = None,
    note: str | None = None,
) -> ReceiptOutcome:
    """Money handed over at the office for the part of the order now due, with
    or without a payment the customer started online. Flushes, no commit."""
    method = _check_method(method)
    provider_code = PROVIDER_BY_METHOD.get(method)
    if provider_code is None:
        raise AppError(
            code="payment.receipt.method_invalid",
            status_code=400,
            message="Un encaissement au comptoir se fait en espèces, par chèque ou virement",
            details={"allowed": sorted(PROVIDER_BY_METHOD)},
        )

    rows = await crud_payment.list_with_status_by_order_id(session, order_id=order.id)
    settled, _pending = settled_by_kind(
        [(p, s) for p, s in rows if s in SETTLED_PAYMENT_STATUSES]
    )
    kind = next_payment_kind(order, settled)
    if kind is None:
        raise AppError(
            code="payment.order.already_paid",
            status_code=409,
            message="Cette commande est déjà réglée",
            details={"order_id": str(order.id)},
        )

    # A manual payment already waiting on this part takes the receipt, even if
    # the customer announced another method (a transfer paid in cash).
    pending_manual = [
        p
        for p, status_name in rows
        if status_name == MANUAL_STATUS_AWAITING_VALIDATION
        and (p.kind or "full") == kind
        and (p.provider_code or "").startswith("manual_")
        and p.is_active
    ]
    if pending_manual:
        payment = pending_manual[-1]
    else:
        currency = order.currency or (rows[0][0].currency if rows else "XPF")
        due = quantize_amount(remaining_amount(order, kind, settled), currency)
        awaiting = await _get_or_create_status(
            session, name=MANUAL_STATUS_AWAITING_VALIDATION
        )
        method_row = (
            await session.exec(
                select(PaymentMethod).where(
                    col(PaymentMethod.provider_code) == provider_code
                )
            )
        ).first()
        payment = Payment(
            order_id=order.id,
            user_id=order.user_id,
            amount=due,
            currency=currency,
            provider_code=provider_code,
            payment_method_id=method_row.id if method_row else None,
            payment_status_id=awaiting.id,
            kind=kind,
            created_at=_now(),
            created_by_id=getattr(admin, "id", None),
        )
        session.add(payment)
        await session.flush()
        payment.provider_reference = str(payment.id)
        session.add(payment)

    return await record_receipt(
        session,
        payment=payment,
        admin=admin,
        amount=amount,
        received_at=received_at,
        method=method,
        reference=reference,
        note=note,
    )


async def next_part_due(
    session: AsyncSession, *, order: Any
) -> tuple[str | None, Decimal]:
    """The part of the order payable now (full, deposit or balance) and what is
    left of it once the settled payments and the instalments already received
    on it are counted: the default of « Enregistrer un encaissement »."""
    rows = await crud_payment.list_with_status_by_order_id(session, order_id=order.id)
    settled, _pending = settled_by_kind(
        [(p, s) for p, s in rows if s in SETTLED_PAYMENT_STATUSES]
    )
    kind = next_payment_kind(order, settled)
    if kind is None:
        return None, _ZERO
    pending_ids = [
        p.id
        for p, s in rows
        if s == MANUAL_STATUS_AWAITING_VALIDATION and (p.kind or "full") == kind
    ]
    partial = sum((await received_by_payment(session, pending_ids)).values(), _ZERO)
    return kind, max(_ZERO, remaining_amount(order, kind, settled) - partial)


@dataclass(slots=True)
class OrderPaymentSummary:
    """Money in and money due on an order, receipts included."""

    paid: Decimal
    due: Decimal
    receipts: list[PaymentReceipt]


async def order_payment_summary(
    session: AsyncSession, *, order: Any
) -> OrderPaymentSummary:
    """``paid`` = settled payments + receipts of payments still pending −
    completed refunds, ``due`` = what is left of the order total."""
    rows = await crud_payment.list_with_status_by_order_id(session, order_id=order.id)
    pending_ids = [p.id for p, s in rows if s not in SETTLED_PAYMENT_STATUSES]
    partial = await received_by_payment(session, pending_ids)
    paid = sum(
        (Decimal(p.amount) for p, s in rows if s in SETTLED_PAYMENT_STATUSES), _ZERO
    ) + sum(partial.values(), _ZERO)
    receipts = list(
        (
            await session.exec(
                select(PaymentReceipt)
                .where(col(PaymentReceipt.order_id) == order.id)
                .order_by(col(PaymentReceipt.received_at))
            )
        ).all()
    )
    # Money handed back no longer counts as paid.
    refunded = (
        await session.exec(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                col(Refund.order_id) == order.id,
                col(Refund.status) == "completed",
            )
        )
    ).one()
    paid -= Decimal(refunded)
    due = max(_ZERO, Decimal(order.total_amount) - paid)
    return OrderPaymentSummary(paid=paid, due=due, receipts=receipts)


__all__ = [
    "DEFAULT_METHOD_BY_PROVIDER",
    "EVENT_PARTIALLY_RECEIVED",
    "EVENT_RECEIPT_CANCELLED",
    "next_part_due",
    "PROVIDER_BY_METHOD",
    "OrderPaymentSummary",
    "ReceiptOutcome",
    "active_receipts",
    "cancel_receipt",
    "order_payment_summary",
    "received_amount",
    "received_by_payment",
    "record_counter_payment",
    "record_receipt",
    "settle_remaining",
]
