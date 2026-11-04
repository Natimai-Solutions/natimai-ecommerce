"""Generic handling of provider notifications and confirmations (R3-P4).

PayZen keeps its historical IPN (``payzen_ipn``), which records its events in
the same journal (:func:`record_webhook_event`); every other API provider
(PayPal today, Stripe later) goes through here. The provider authenticates
and normalizes its notification into a :class:`ProviderOutcome`; this module
applies it to the payment with the same guarantees as the PayZen IPN:

* a notification delivered twice is applied once (``payment_webhook_events``
  plus the payment's own status);
* a terminal status never flips to another terminal status (paid → failed);
* the amount charged must be the amount asked, or the payment stays
  un-completed for manual review;
* the order status follows through the outbox (``payment.captured`` /
  ``payment.rejected``), exactly like PayZen.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.payment_webhook_event import PaymentWebhookEvent
from app.features.payment.providers.base import (
    OUTCOME_AUTHORIZED,
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_REFUNDED,
    ProviderOutcome,
)
from app.outbox.registry import outbox_registry
from app.utils.money import decimal_to_minor_units

logger = logging.getLogger(__name__)

STATUS_COMPLETED = "Completed"
STATUS_AUTHORIZED = "Authorized"
STATUS_FAILED = "Failed"

_STATUS_FOR_OUTCOME: dict[str, str] = {
    OUTCOME_COMPLETED: STATUS_COMPLETED,
    OUTCOME_AUTHORIZED: STATUS_AUTHORIZED,
    OUTCOME_FAILED: STATUS_FAILED,
}
_EVENT_FOR_OUTCOME: dict[str, str] = {
    OUTCOME_COMPLETED: "payment.captured",
    OUTCOME_FAILED: "payment.rejected",
}
_SUCCESS = {OUTCOME_COMPLETED, OUTCOME_AUTHORIZED}
# A payment in one of these statuses is decided: a contradicting outcome is a
# provider inconsistency, logged and never applied. Authorized → Completed is
# the normal capture path and stays allowed.
_TERMINAL_STATUSES = {
    STATUS_COMPLETED,
    STATUS_FAILED,
    "Refunded",
    "PartiallyRefunded",
    # Closed by the customer's cancellation: a late success must not revive
    # the order (it is logged as a conflict for the shop to refund).
    "Cancelled",
}

RESULT_APPLIED = "applied"
RESULT_DUPLICATE = "duplicate"
RESULT_CONFLICT = "conflict"
RESULT_AMOUNT_MISMATCH = "amount_mismatch"
RESULT_IGNORED = "ignored"
RESULT_UNKNOWN_PAYMENT = "unknown_payment"


@dataclass(slots=True)
class PipelineResult:
    result: str
    payment_id: uuid.UUID | None = None
    status_name: str | None = None


def expected_charge(payment: Payment) -> tuple[int, str]:
    """What the provider was asked to charge, in minor units.

    A provider that charges in another currency than the order (PayPal in EUR
    for an XPF order) records ``charged_amount_minor`` / ``charged_currency``
    at initiation; otherwise the payment's own amount is the reference.
    """
    data = payment.provider_data if isinstance(payment.provider_data, dict) else {}
    charged = data.get("charged_amount_minor")
    charged_currency = data.get("charged_currency")
    if charged is not None and charged_currency:
        return int(charged), str(charged_currency).upper()
    return (
        decimal_to_minor_units(payment.amount, payment.currency),
        payment.currency.upper(),
    )


async def find_payment(
    session: AsyncSession, *, provider_code: str, reference: str | None
) -> Payment | None:
    """Our payment behind a provider reference (its id, or the reference
    recorded at initiation)."""
    if not reference:
        return None
    try:
        payment_id = uuid.UUID(reference)
    except ValueError:
        payment_id = None
    if payment_id is not None:
        payment = await session.get(Payment, payment_id)
        if payment is not None and payment.provider_code == provider_code:
            return payment
    return (
        await session.exec(
            select(Payment).where(
                col(Payment.provider_code) == provider_code,
                col(Payment.provider_reference) == reference,
            )
        )
    ).first()


async def lock_payment(session: AsyncSession, payment: Payment) -> Payment:
    """The payment row, locked until the commit and read again under the lock.

    Providers retry and sometimes deliver the same notification twice at
    once: without the lock both deliveries read the payment as not yet
    processed and both apply it (two ``payment.captured``, two invoices…).
    The second one now waits, then sees the first one's work as a duplicate.
    """
    return (
        await session.exec(
            select(Payment)
            .where(col(Payment.id) == payment.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()


async def _status_name(session: AsyncSession, payment: Payment) -> str | None:
    if payment.payment_status_id is None:
        return None
    record = await session.get(PaymentStatus, payment.payment_status_id)
    return record.name if record is not None else None


class WebhookEventAlreadyRecorded(Exception):
    """The provider event was already processed (same provider, same id)."""


_AlreadyRecorded = WebhookEventAlreadyRecorded


async def record_webhook_event(
    session: AsyncSession,
    *,
    provider_code: str,
    event_id: str | None,
    event_type: str | None,
    payment_id: uuid.UUID | None,
    outcome: str,
) -> PaymentWebhookEvent | None:
    """Remember a provider event in the shared journal (None when it has no id).

    Every provider goes through here, the PayZen IPN included: one journal of
    what was received and what was done with it. The caller updates
    ``event.outcome`` once it knows. Raises :class:`WebhookEventAlreadyRecorded`
    when the event was already processed.
    """
    if not event_id:
        return None
    event_id = event_id[:255]
    already = (
        await session.exec(
            select(PaymentWebhookEvent.id).where(
                col(PaymentWebhookEvent.provider_code) == provider_code,
                col(PaymentWebhookEvent.event_id) == event_id,
            )
        )
    ).first()
    if already is not None:
        raise WebhookEventAlreadyRecorded
    event = PaymentWebhookEvent(
        provider_code=provider_code,
        event_id=event_id,
        event_type=(event_type or "")[:100] or None,
        payment_id=payment_id,
        outcome=outcome,
    )
    session.add(event)
    return event


async def _record_event(
    session: AsyncSession,
    outcome: ProviderOutcome,
    *,
    payment_id: uuid.UUID | None,
    result: str,
) -> PaymentWebhookEvent | None:
    return await record_webhook_event(
        session,
        provider_code=outcome.provider_code,
        event_id=outcome.event_id,
        event_type=outcome.event_type,
        payment_id=payment_id,
        outcome=result,
    )


async def _publish(
    session: AsyncSession,
    *,
    event_type: str,
    payment: Payment,
    outcome: ProviderOutcome,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    await outbox_registry.publish(
        session=session,
        event_type=event_type,
        payload={
            "payment_id": str(payment.id),
            "order_id": str(payment.order_id) if payment.order_id else None,
            "user_id": str(payment.user_id) if payment.user_id else None,
            "provider_code": outcome.provider_code,
            "provider_reference": payment.provider_reference,
            "total_amount": str(payment.amount),
            "currency": payment.currency,
            "action": action,
            "admin_user_id": None,
            "reason": None,
            "reference": outcome.transaction_id,
            "metadata": {
                "outcome": outcome.status,
                "event_type": outcome.event_type,
                "transaction_id": outcome.transaction_id,
                **(metadata or {}),
            },
        },
        correlation_id=payment.id,
    )


async def apply_provider_outcome(
    session: AsyncSession,
    outcome: ProviderOutcome,
    *,
    payment: Payment | None = None,
    action: str = "webhook",
) -> PipelineResult:
    """Apply a normalized provider outcome to its payment. Commits.

    ``payment`` is passed by the confirmation endpoint (the customer's own
    payment); a webhook finds it from ``outcome.payment_reference``.
    """
    if payment is None:
        payment = await find_payment(
            session,
            provider_code=outcome.provider_code,
            reference=outcome.payment_reference,
        )
    if payment is None:
        logger.warning(
            "%s notification %s for an unknown payment %r ignored",
            outcome.provider_code,
            outcome.event_type,
            outcome.payment_reference,
        )
        try:
            await _record_event(
                session, outcome, payment_id=None, result=RESULT_UNKNOWN_PAYMENT
            )
        except _AlreadyRecorded:
            return PipelineResult(RESULT_DUPLICATE)
        await _commit(session)
        return PipelineResult(RESULT_UNKNOWN_PAYMENT)

    payment = await lock_payment(session, payment)
    payment_id = payment.id
    current = await _status_name(session, payment)
    target = _STATUS_FOR_OUTCOME.get(outcome.status or "")

    def done(result: str, status_name: str | None = current) -> PipelineResult:
        return PipelineResult(result, payment_id=payment_id, status_name=status_name)

    try:
        event = await _record_event(
            session, outcome, payment_id=payment_id, result=_pending_result(outcome)
        )
    except _AlreadyRecorded:
        return done(RESULT_DUPLICATE)

    def mark(result: str) -> None:
        if event is not None:
            event.outcome = result

    await _publish(
        session,
        event_type="payment.webhook_received",
        payment=payment,
        outcome=outcome,
        action=f"{action}_received",
        metadata={"payload": outcome.payload},
    )

    if outcome.status == OUTCOME_REFUNDED or target is None:
        # Refunds are driven from the back office (refund_service); the
        # provider's echo is only kept for the record.
        await _commit(session)
        return done(RESULT_IGNORED)

    if current == target:
        mark(RESULT_DUPLICATE)
        await _commit(session)
        return done(RESULT_DUPLICATE)

    if current in _TERMINAL_STATUSES:
        logger.warning(
            "Conflicting %s outcome ignored for payment_id=%s: current=%s incoming=%s",
            outcome.provider_code,
            payment_id,
            current,
            target,
        )
        mark(RESULT_CONFLICT)
        await _commit(session)
        return done(RESULT_CONFLICT)

    provider_data = (
        dict(payment.provider_data) if isinstance(payment.provider_data, dict) else {}
    )
    if outcome.status in _SUCCESS and outcome.amount_minor is not None:
        expected_minor, expected_currency = expected_charge(payment)
        received_currency = (outcome.currency or expected_currency).upper()
        if (
            outcome.amount_minor != expected_minor
            or received_currency != expected_currency
        ):
            logger.error(
                "%s amount mismatch for payment_id=%s: expected=%s %s received=%s %s "
                "— payment left un-completed for manual review",
                outcome.provider_code,
                payment_id,
                expected_minor,
                expected_currency,
                outcome.amount_minor,
                received_currency,
            )
            provider_data["amount_mismatch"] = {
                "expected_minor": expected_minor,
                "expected_currency": expected_currency,
                "received_minor": outcome.amount_minor,
                "received_currency": received_currency,
                "transaction_id": outcome.transaction_id,
            }
            payment.provider_data = provider_data
            session.add(payment)
            mark(RESULT_AMOUNT_MISMATCH)
            await _commit(session)
            return done(RESULT_AMOUNT_MISMATCH)

    provider_data.update(outcome.extra)
    provider_data["provider_status"] = outcome.status
    if outcome.transaction_id:
        provider_data["transaction_id"] = outcome.transaction_id
    payment.provider_data = provider_data
    status_record = await crud_payment_status.get_by_name(session, name=target)
    if status_record is None:
        status_record = PaymentStatus(
            name=target, description=f"Auto-created by provider webhook: {target}"
        )
        session.add(status_record)
        await session.flush()
    payment.payment_status_id = status_record.id
    session.add(payment)

    event_type = _EVENT_FOR_OUTCOME.get(outcome.status or "")
    if event_type is not None:
        await _publish(
            session,
            event_type=event_type,
            payment=payment,
            outcome=outcome,
            action=action,
        )
    await _commit(session)
    logger.info(
        "%s outcome applied: payment_id=%s %s → %s",
        outcome.provider_code,
        payment_id,
        current,
        target,
    )
    return done(RESULT_APPLIED, target)


def _pending_result(outcome: ProviderOutcome) -> str:
    return RESULT_APPLIED if outcome.status in _STATUS_FOR_OUTCOME else RESULT_IGNORED


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError:
        # The same event delivered twice at the same instant: the other
        # delivery won the unique constraint and applied it.
        await session.rollback()
        logger.info("Concurrent duplicate provider notification ignored")


__all__ = [
    "WebhookEventAlreadyRecorded",
    "record_webhook_event",
    "PipelineResult",
    "RESULT_AMOUNT_MISMATCH",
    "RESULT_APPLIED",
    "RESULT_CONFLICT",
    "RESULT_DUPLICATE",
    "RESULT_IGNORED",
    "RESULT_UNKNOWN_PAYMENT",
    "apply_provider_outcome",
    "expected_charge",
    "find_payment",
]
