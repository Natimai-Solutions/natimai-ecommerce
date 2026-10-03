from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import RecordNotFoundError
from app.features.inventory.services.stock_release import (
    confirm_order_stock,
    release_order_stock,
)
from app.features.invoice.services.credit_note_service import (
    CreditNoteIssuanceError,
    issue_credit_note_for_refund,
)
from app.features.invoice.services.invoice_service import issue_invoice_for_order
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus, OrderStatusCreate
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import Payment
from app.features.payment.services.deposit import (
    KIND_BALANCE,
    KIND_DEPOSIT,
    KIND_FULL,
    ORDER_STATUS_DEPOSIT_PAID,
)
from app.features.payment.services.notifications import (
    send_payment_event_notifications,
)
from app.features.payment.services.store_credit import part_coverage
from app.outbox.decorators import outbox_handler
from app.outbox.registry import outbox_registry

logger = logging.getLogger(__name__)

ORDER_STATUS_PAID = "Paid"
ORDER_STATUS_PAYMENT_FAILED = "PaymentFailed"
ORDER_STATUS_AWAITING_PAYMENT = "AwaitingPayment"
ORDER_STATUS_REFUNDED = "Refunded"
ORDER_STATUS_PARTIALLY_REFUNDED = "PartiallyRefunded"
#: Some money received on a manual payment, not yet the whole part (R3-P2).
ORDER_STATUS_PARTIALLY_PAID = "PartiallyPaid"
#: Order statuses a receipt may move: before the part is paid. A receipt on the
#: balance of a deposit order never touches its fulfilment status.
_BEFORE_PAYMENT_ORDER_STATUSES: frozenset[str] = frozenset(
    {"Pending", "AwaitingPayment", "PartiallyPaid", "PaymentFailed"}
)
# Terminal-for-automation status: money was taken but the amounts disagree, so a
# human must decide. Never set by the nominal flow — see
# ``_handle_captured_amount_mismatch``.
ORDER_STATUS_PAYMENT_REVIEW = "PaymentReview"

#: Emitted once the accounting invoice exists, so its delivery e-mail retries
#: independently of the issuance itself.
EVENT_INVOICE_ISSUED = "invoice.issued"
EVENT_CREDIT_NOTE_ISSUED = "credit_note.issued"

EVENT_WEBHOOK_RECEIVED = "payment.webhook_received"
EVENT_AWAITING_VALIDATION = "payment.awaiting_validation"
EVENT_DOCUMENT_REQUIRED = "payment.document_required"
EVENT_CAPTURED = "payment.captured"
EVENT_REJECTED = "payment.rejected"
EVENT_DOCUMENT_INFECTED = "payment.document_infected"
EVENT_AMOUNT_MISMATCH = "payment.amount_mismatch"

__all__ = [
    "crud_order",
    "crud_order_status",
    "crud_payment",
    "on_payment_awaiting_validation",
    "on_payment_captured",
    "on_payment_captured_issue_invoice",
    "on_payment_partially_received",
    "on_payment_receipt_cancelled",
    "on_payment_refunded",
    "on_payment_rejected",
    "on_payment_document_required",
    "on_payment_document_uploaded",
    "on_payment_document_infected",
    "on_payment_webhook_received",
    "on_payment_awaiting_validation_notify",
    "on_payment_document_required_notify",
    "on_payment_captured_notify",
    "on_payment_rejected_notify",
    "on_payment_document_infected_notify",
]


def _parse_order_id(payload: dict[str, Any]) -> uuid.UUID | None:
    """Order id from an outbox payment payload, or None."""
    raw_order_id = payload.get("order_id")
    if not raw_order_id:
        return None
    try:
        return uuid.UUID(str(raw_order_id))
    except (TypeError, ValueError):
        return None


async def _get_or_create_order_status_id(
    session: AsyncSession, *, name: str
) -> uuid.UUID:
    """Get or create order status id."""
    status = await crud_order_status.get_by_name(session, name=name)
    if status is not None:
        return status.id

    created = await crud_order_status.create_draft(
        session=session,
        data=OrderStatusCreate(name=name),
        user=None,
    )
    await session.flush()
    return created.id


async def _sync_order_status(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    target_status_name: str,
) -> None:
    """Synchronize order status."""
    raw_order_id = payload.get("order_id")
    if not raw_order_id:
        logger.debug(
            "Skipping order status sync for payment %s — no order_id in payload",
            payload.get("payment_id"),
        )
        return

    try:
        order_uuid = uuid.UUID(str(raw_order_id))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid order_id '%s' in payment event payload — skipping order sync",
            raw_order_id,
        )
        return

    order = await crud_order.read(session, id=order_uuid)
    if order is None:
        logger.warning(
            "Order %s not found while syncing status %s",
            order_uuid,
            target_status_name,
        )
        return

    status_id = await _get_or_create_order_status_id(session, name=target_status_name)
    order.order_status_id = status_id
    session.add(order)
    await session.commit()


async def _notify_payment_event(
    session: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Execute notify payment event."""
    try:
        await send_payment_event_notifications(
            session=session,
            event_type=event_type,
            payload=payload,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error while notifying payment event %s: %s",
            event_type,
            exc,
        )


@outbox_handler("payment.awaiting_validation")
async def on_payment_awaiting_validation(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment awaiting validation event."""
    logger.info(
        "Payment awaiting manual validation: payment_id=%s order_id=%s provider=%s",
        payload.get("payment_id"),
        payload.get("order_id"),
        payload.get("provider_code"),
    )
    await _sync_order_status(
        session,
        payload=payload,
        target_status_name=ORDER_STATUS_AWAITING_PAYMENT,
    )


async def _load_payment_and_order(
    session: AsyncSession, payload: dict[str, Any]
) -> tuple[Payment | None, Order | None]:
    """The payment and order of an outbox payment payload (None, None when
    either is missing or unloadable — replayed or partial payloads keep the
    historical behaviour)."""
    order_id = _parse_order_id(payload)
    raw_payment_id = payload.get("payment_id")
    if order_id is None or not raw_payment_id:
        return None, None
    try:
        payment_id = uuid.UUID(str(raw_payment_id))
    except (TypeError, ValueError):
        return None, None
    try:
        payment = await crud_payment.read(session, id=payment_id)
        order = await crud_order.read(session, id=order_id)
    except RecordNotFoundError:
        return None, None
    if payment is None or order is None:
        return None, None
    return payment, order


def _payment_kind(payment: Payment | None) -> str:
    kind = getattr(payment, "kind", None)
    return kind if isinstance(kind, str) and kind else KIND_FULL


#: Sentinel of ``_captured_amount_mismatch``: the part is not fully covered
#: yet but another payment on it is still pending (a store credit next to a
#: card payment): nothing to do until the other one lands.
PARTIAL = "partial"


async def _captured_amount_mismatch(
    session: AsyncSession, *, payload: dict[str, Any]
) -> dict[str, str] | str | None:
    """Last line of defence before flipping an order to Paid.

    Returns the mismatch details when the payments settled on the part this
    capture belongs to (the total, or the deposit / balance of a deposit
    order) do not add up to what it is worth, :data:`PARTIAL` when they fall
    short but another payment on that part is still pending, or ``None`` when
    the part is exactly covered — or simply cannot be checked.
    """
    payment, order = await _load_payment_and_order(session, payload)
    if payment is None or order is None:
        return None

    covered, expected, still_pending = await part_coverage(
        session, payment=payment, order=order
    )
    if covered == expected:
        return None
    if covered < expected and still_pending:
        return PARTIAL

    return {
        "expected_amount": str(expected),
        "received_amount": str(covered),
        "currency": str(payment.currency),
    }


async def _handle_captured_amount_mismatch(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    mismatch: dict[str, str],
) -> None:
    """Park the order for human arbitration instead of marking it Paid.

    The money was taken but the amounts disagree, so three things must happen —
    and silently returning did none of them:

    * the order moves to ``PaymentReview`` so the incident is visible in the
      back-office (and so ``POST /payments/initiate`` refuses a second charge);
    * the checkout stock reservations stay PENDING — neither confirmed (the
      order is not fulfillable) nor released (the customer has paid);
    * the admins are notified, because the outbox marks this delivery as
      processed and will never replay it.
    """
    logger.error(
        "payment.captured amount mismatch: payment %s amount=%s does not cover "
        "order %s total=%s — order parked in %s for manual review",
        payload.get("payment_id"),
        mismatch["received_amount"],
        payload.get("order_id"),
        mismatch["expected_amount"],
        ORDER_STATUS_PAYMENT_REVIEW,
    )
    await _sync_order_status(
        session,
        payload=payload,
        target_status_name=ORDER_STATUS_PAYMENT_REVIEW,
    )
    await _notify_payment_event(
        session,
        event_type=EVENT_AMOUNT_MISMATCH,
        payload={
            **payload,
            "amount": mismatch["received_amount"],
            "currency": mismatch["currency"],
            "reason": (
                f"Montant encaisse {mismatch['received_amount']} "
                f"{mismatch['currency']} != total commande "
                f"{mismatch['expected_amount']} — commande bloquee en "
                f"{ORDER_STATUS_PAYMENT_REVIEW}, stock non confirme."
            ),
        },
    )


@outbox_handler("payment.captured")
async def on_payment_captured(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Handle the payment captured event."""
    logger.info(
        "Payment captured: payment_id=%s order_id=%s",
        payload.get("payment_id"),
        payload.get("order_id"),
    )
    mismatch = await _captured_amount_mismatch(session, payload=payload)
    if mismatch == PARTIAL:
        logger.info(
            "payment.captured: order %s part still awaiting another payment",
            payload.get("order_id"),
        )
        return
    if isinstance(mismatch, dict):
        await _handle_captured_amount_mismatch(
            session, payload=payload, mismatch=mismatch
        )
        return
    payment, order = await _load_payment_and_order(session, payload)
    kind = _payment_kind(payment)
    if kind == KIND_BALANCE and order is not None:
        # The goods were bought and reserved on the deposit; the balance only
        # settles the order. « DepositPaid » becomes « Paid »; a fulfilment
        # status (Received…) is kept, the customer follows the departure.
        order.balance_paid_at = datetime.now(UTC)
        session.add(order)
        current = await session.get(OrderStatus, order.order_status_id)
        if current is not None and current.name == ORDER_STATUS_DEPOSIT_PAID:
            await _sync_order_status(
                session, payload=payload, target_status_name=ORDER_STATUS_PAID
            )
        await session.commit()
        return
    await _sync_order_status(
        session,
        payload=payload,
        target_status_name=(
            ORDER_STATUS_DEPOSIT_PAID if kind == KIND_DEPOSIT else ORDER_STATUS_PAID
        ),
    )
    # The stock reserved at checkout is now definitively consumed.
    order_id = _parse_order_id(payload)
    if order_id is not None:
        confirmed = await confirm_order_stock(session, order_id=order_id)
        if confirmed:
            await session.commit()
            logger.info(
                "Stock reservations confirmed for order %s (%d movement(s))",
                order_id,
                confirmed,
            )


async def _receipt_status_sync(
    session: AsyncSession, *, payload: dict[str, Any], target_status_name: str
) -> None:
    """Move the order to ``target_status_name`` after a receipt, unless the
    receipt is on a balance or the order already left the payment stage."""
    if (payload.get("kind") or KIND_FULL) == KIND_BALANCE:
        return
    order_id = _parse_order_id(payload)
    if order_id is None:
        return
    order = await session.get(Order, order_id)
    if order is None:
        return
    current = await session.get(OrderStatus, order.order_status_id)
    if current is not None and current.name not in _BEFORE_PAYMENT_ORDER_STATUSES:
        return
    await _sync_order_status(
        session, payload=payload, target_status_name=target_status_name
    )


@outbox_handler("payment.partially_received")
async def on_payment_partially_received(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """An instalment was received: the order is « partiellement payée »."""
    logger.info(
        "Payment partially received: payment_id=%s order_id=%s received=%s left=%s",
        payload.get("payment_id"),
        payload.get("order_id"),
        payload.get("received_amount"),
        payload.get("remaining_amount"),
    )
    await _receipt_status_sync(
        session, payload=payload, target_status_name=ORDER_STATUS_PARTIALLY_PAID
    )


@outbox_handler("payment.receipt_cancelled")
async def on_payment_receipt_cancelled(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """A receipt was cancelled (bounced cheque…): back to « partiellement
    payée », or to « en attente de paiement » when nothing is left."""
    try:
        received = Decimal(str(payload.get("received_amount") or "0"))
    except ArithmeticError:
        received = Decimal("0")
    await _receipt_status_sync(
        session,
        payload=payload,
        target_status_name=(
            ORDER_STATUS_PARTIALLY_PAID
            if received > 0
            else ORDER_STATUS_AWAITING_PAYMENT
        ),
    )


@outbox_handler("payment.captured")
async def on_payment_captured_issue_invoice(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Issue the accounting invoice once the payment is captured (M3).

    Separate handler on purpose: an invoicing failure retries on its own
    (ARQ backoff) without re-running the order status sync or the stock
    confirmation. Issuance is idempotent, so a retry never duplicates the
    document.
    """
    order_id = _parse_order_id(payload)
    if order_id is None:
        return

    # Same guard as the status sync: never invoice an order whose captured
    # payment does not cover its part.
    mismatch = await _captured_amount_mismatch(session, payload=payload)
    if mismatch == PARTIAL:
        return
    if isinstance(mismatch, dict):
        logger.error(
            "Invoice not issued for order %s: captured amount %s does not cover "
            "the amount due %s",
            order_id,
            mismatch["received_amount"],
            mismatch["expected_amount"],
        )
        return
    # A deposit gets a receipt (the capture e-mail), not an invoice: the one
    # invoice of the order is issued when the balance settles it.
    payment, _order = await _load_payment_and_order(session, payload)
    if _payment_kind(payment) == KIND_DEPOSIT:
        logger.info(
            "Order %s: deposit captured, invoice deferred to the balance", order_id
        )
        return

    invoice = await issue_invoice_for_order(session, order_id=order_id)
    logger.info("Invoice %s available for order %s", invoice.invoice_number, order_id)

    # Issuing is not delivering. The invoice used to sit in the database until
    # the customer thought to look for it; the law expects it to be handed
    # over. A dedicated event keeps the e-mail retrying on its own without
    # re-running the (already idempotent) issuance.
    await outbox_registry.publish(
        session=session,
        event_type=EVENT_INVOICE_ISSUED,
        payload={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "order_id": str(order_id),
            "user_id": str(invoice.user_id),
            "currency": invoice.currency,
            "total_incl_tax": str(invoice.total_incl_tax),
            "total_tax": str(invoice.total_tax),
        },
        correlation_id=order_id,
    )
    await session.commit()


@outbox_handler("payment.refunded")
async def on_payment_refunded(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Sync the order status when a payment is (partially) refunded."""
    fully = bool(payload.get("fully_refunded"))
    logger.info(
        "Payment refunded: payment_id=%s order_id=%s fully=%s amount=%s",
        payload.get("payment_id"),
        payload.get("order_id"),
        fully,
        payload.get("amount"),
    )
    await _sync_order_status(
        session,
        payload=payload,
        target_status_name=(
            ORDER_STATUS_REFUNDED if fully else ORDER_STATUS_PARTIALLY_REFUNDED
        ),
    )
    # Only a *fully* refunded order gives its stock back, and only the
    # reservations still PENDING. A captured payment has already confirmed its
    # movements (COMPLETED), so this is a no-op on the normal flow — it exists
    # for the authorise-then-refund case, where the funds were never captured
    # and the reservation would otherwise be held forever.
    if not fully:
        return
    order_id = _parse_order_id(payload)
    if order_id is not None:
        released = await release_order_stock(session, order_id=order_id)
        if released:
            await session.commit()
            logger.info(
                "Stock released for fully refunded order %s (%d uncaptured "
                "reservation(s))",
                order_id,
                released,
            )


@outbox_handler("payment.refunded")
async def on_payment_refunded_issue_credit_note(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Issue the credit note that corrects the invoice (Z2).

    A refund used to move money and a payment status, leaving the invoice in
    the books claiming a sale that no longer held. An issued invoice cannot be
    edited — its sequence is gap-free by law — so the correction is a separate
    document pointing at it.

    Separate handler on purpose, like the invoice issuance: a failure here
    retries on its own without re-running the status sync or the stock release.
    """
    raw_refund_id = payload.get("refund_id")
    if not raw_refund_id:
        # Pre-existing events carry no refund id; nothing to key idempotency on.
        logger.warning("credit note: no refund_id in payload, skipping")
        return
    try:
        refund_id = uuid.UUID(str(raw_refund_id))
    except (TypeError, ValueError):
        logger.warning("credit note: invalid refund_id %r", raw_refund_id)
        return

    try:
        credit_note = await issue_credit_note_for_refund(session, refund_id=refund_id)
    except CreditNoteIssuanceError as exc:
        # An order refunded before it was ever invoiced has nothing to correct;
        # retrying would never succeed, so log loudly and stop.
        logger.error("Credit note not issued for refund %s: %s", refund_id, exc)
        return

    logger.info(
        "Credit note %s issued for refund %s",
        credit_note.credit_note_number,
        refund_id,
    )

    # Issuing is not delivering (same rule as the invoice): a dedicated event
    # e-mails the document and retries on its own. Issuance is idempotent, so
    # a replay re-publishes for the same note; ``emailed_at`` stops the mail.
    await outbox_registry.publish(
        session=session,
        event_type=EVENT_CREDIT_NOTE_ISSUED,
        payload={
            "credit_note_id": str(credit_note.id),
            "credit_note_number": credit_note.credit_note_number,
            "invoice_id": str(credit_note.invoice_id),
            "order_id": str(credit_note.order_id),
            "user_id": str(credit_note.user_id),
            "currency": credit_note.currency,
            "total_incl_tax": str(credit_note.total_incl_tax),
            "total_tax": str(credit_note.total_tax),
            "reason": credit_note.reason or "",
        },
        correlation_id=credit_note.order_id,
    )
    await session.commit()


@outbox_handler("payment.rejected")
async def on_payment_rejected(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Handle the payment rejected event."""
    logger.info(
        "Payment rejected: payment_id=%s order_id=%s reason=%s",
        payload.get("payment_id"),
        payload.get("order_id"),
        payload.get("reason"),
    )
    # A refused balance does not undo the order: the deposit is in, the goods
    # are bought and reserved. The customer simply retries from their account.
    payment, _order = await _load_payment_and_order(session, payload)
    if _payment_kind(payment) == KIND_BALANCE:
        return
    await _sync_order_status(
        session, payload=payload, target_status_name=ORDER_STATUS_PAYMENT_FAILED
    )
    # Give the reserved stock back: the order will never be fulfilled.
    # (Historically nothing compensated the checkout decrement — oversell.)
    order_id = _parse_order_id(payload)
    if order_id is not None:
        released = await release_order_stock(session, order_id=order_id)
        if released:
            await session.commit()
            logger.info(
                "Stock released for rejected order %s (%d movement(s))",
                order_id,
                released,
            )


@outbox_handler("payment.document_required")
async def on_payment_document_required(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment document required event."""
    logger.info(
        "Payment requires document upload: payment_id=%s order_id=%s",
        payload.get("payment_id"),
        payload.get("order_id"),
    )
    await _sync_order_status(
        session,
        payload=payload,
        target_status_name=ORDER_STATUS_AWAITING_PAYMENT,
    )


@outbox_handler("payment.document_uploaded")
async def on_payment_document_uploaded(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Run antivirus scan asynchronously after a document upload is confirmed.

    On infection: transition the payment via `mark_document_infected`,
    which publishes `payment.document_infected` for downstream notifications.
    """
    import uuid as _uuid

    from app.features.attachment.antivirus.factory import get_antivirus_scanner
    from app.features.attachment.storage.factory import get_file_storage
    from app.features.payment.crud.payment import crud_payment
    from app.features.payment.crud.payment_attachment import (
        crud_payment_attachment,
    )
    from app.features.payment.services.document_payment import (
        mark_document_infected,
    )

    attachment_id_raw = payload.get("attachment_id")
    payment_id_raw = payload.get("payment_id")
    if not attachment_id_raw or not payment_id_raw:
        logger.warning("Missing attachment_id/payment_id in payload — skipping scan")
        return

    try:
        attachment_id = _uuid.UUID(str(attachment_id_raw))
        payment_id = _uuid.UUID(str(payment_id_raw))
    except (TypeError, ValueError):
        logger.warning("Invalid UUIDs in document_uploaded payload — skipping")
        return

    try:
        attachment = await crud_payment_attachment.read(session, id=attachment_id)
        payment = await crud_payment.read(session, id=payment_id)
    except Exception as e:
        logger.warning("Cannot load attachment/payment for AV scan: %s", e)
        return

    storage = get_file_storage()
    scanner = get_antivirus_scanner()

    logger.info(
        "AV scan starting: payment=%s attachment=%s key=%s",
        payment_id,
        attachment_id,
        attachment.file_key,
    )

    try:
        data = await storage.get_bytes(key=attachment.file_key)
        result = await scanner.scan_bytes(data)
    except Exception as e:
        # Re-raise so the ARQ job is retried (e.g. ClamAV not ready yet, or the
        # file not yet visible). Swallowing here left the attachment stuck on
        # "analyse…" forever with no retry.
        logger.error(
            "AV scan failed for attachment %s: %s — will retry", attachment_id, e
        )
        raise

    attachment.av_scanned = True
    attachment.av_clean = result.is_clean
    attachment.av_signature = result.signature
    session.add(attachment)
    logger.info(
        "AV scan complete: attachment=%s clean=%s", attachment_id, result.is_clean
    )

    if not result.is_clean:
        try:
            await storage.delete(key=attachment.file_key)
        except Exception:
            pass
        await mark_document_infected(
            session,
            payment=payment,
            attachment=attachment,
            signature=result.signature,
        )

    await session.commit()


@outbox_handler("payment.document_infected")
async def on_payment_document_infected(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment document infected event."""
    logger.error(
        "Document flagged as infected: payment_id=%s attachment_id=%s signature=%s",
        payload.get("payment_id"),
        payload.get("attachment_id"),
        (payload.get("metadata") or {}).get("signature"),
    )
    await _sync_order_status(
        session,
        payload=payload,
        target_status_name=ORDER_STATUS_PAYMENT_FAILED,
    )


@outbox_handler(EVENT_WEBHOOK_RECEIVED)
async def on_payment_webhook_received(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment webhook received event."""
    logger.info(
        "Payment webhook received: payment_id=%s provider=%s",
        payload.get("payment_id"),
        payload.get("provider_code"),
    )
    await _notify_payment_event(
        session, event_type=EVENT_WEBHOOK_RECEIVED, payload=payload
    )


@outbox_handler(EVENT_AWAITING_VALIDATION)
async def on_payment_awaiting_validation_notify(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment awaiting validation notify event."""
    await _notify_payment_event(
        session, event_type=EVENT_AWAITING_VALIDATION, payload=payload
    )


@outbox_handler(EVENT_DOCUMENT_REQUIRED)
async def on_payment_document_required_notify(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment document required notify event."""
    await _notify_payment_event(
        session, event_type=EVENT_DOCUMENT_REQUIRED, payload=payload
    )


@outbox_handler(EVENT_CAPTURED)
async def on_payment_captured_notify(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment captured notify event."""
    await _notify_payment_event(session, event_type=EVENT_CAPTURED, payload=payload)


@outbox_handler(EVENT_REJECTED)
async def on_payment_rejected_notify(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment rejected notify event."""
    await _notify_payment_event(session, event_type=EVENT_REJECTED, payload=payload)


@outbox_handler(EVENT_DOCUMENT_INFECTED)
async def on_payment_document_infected_notify(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Handle the payment document infected notify event."""
    await _notify_payment_event(
        session, event_type=EVENT_DOCUMENT_INFECTED, payload=payload
    )
