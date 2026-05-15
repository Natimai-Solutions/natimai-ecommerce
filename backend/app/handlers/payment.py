from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order_status import OrderStatusCreate
from app.features.payment.services.notifications import (
    send_payment_event_notifications,
)
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)

ORDER_STATUS_PAID = "Paid"
ORDER_STATUS_PAYMENT_FAILED = "PaymentFailed"
ORDER_STATUS_AWAITING_PAYMENT = "AwaitingPayment"

EVENT_WEBHOOK_RECEIVED = "payment.webhook_received"
EVENT_AWAITING_VALIDATION = "payment.awaiting_validation"
EVENT_DOCUMENT_REQUIRED = "payment.document_required"
EVENT_CAPTURED = "payment.captured"
EVENT_REJECTED = "payment.rejected"
EVENT_DOCUMENT_INFECTED = "payment.document_infected"


async def _get_or_create_order_status_id(
    session: AsyncSession, *, name: str
) -> uuid.UUID:
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
    *,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    try:
        await send_payment_event_notifications(event_type=event_type, payload=payload)
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


@outbox_handler("payment.captured")
async def on_payment_captured(session: AsyncSession, payload: dict[str, Any]) -> None:
    logger.info(
        "Payment captured: payment_id=%s order_id=%s",
        payload.get("payment_id"),
        payload.get("order_id"),
    )
    await _sync_order_status(
        session, payload=payload, target_status_name=ORDER_STATUS_PAID
    )


@outbox_handler("payment.rejected")
async def on_payment_rejected(session: AsyncSession, payload: dict[str, Any]) -> None:
    logger.info(
        "Payment rejected: payment_id=%s order_id=%s reason=%s",
        payload.get("payment_id"),
        payload.get("order_id"),
        payload.get("reason"),
    )
    await _sync_order_status(
        session, payload=payload, target_status_name=ORDER_STATUS_PAYMENT_FAILED
    )


@outbox_handler("payment.document_required")
async def on_payment_document_required(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
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

    try:
        data = await storage.get_bytes(key=attachment.file_key)
        result = await scanner.scan_bytes(data)
    except Exception as e:
        logger.error("AV scan failed for attachment %s: %s", attachment_id, e)
        return

    attachment.av_scanned = True
    attachment.av_clean = result.is_clean
    attachment.av_signature = result.signature
    session.add(attachment)

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
    _session: AsyncSession, payload: dict[str, Any]
) -> None:
    logger.info(
        "Payment webhook received: payment_id=%s provider=%s",
        payload.get("payment_id"),
        payload.get("provider_code"),
    )
    await _notify_payment_event(event_type=EVENT_WEBHOOK_RECEIVED, payload=payload)


@outbox_handler(EVENT_AWAITING_VALIDATION)
async def on_payment_awaiting_validation_notify(
    _session: AsyncSession, payload: dict[str, Any]
) -> None:
    await _notify_payment_event(event_type=EVENT_AWAITING_VALIDATION, payload=payload)


@outbox_handler(EVENT_DOCUMENT_REQUIRED)
async def on_payment_document_required_notify(
    _session: AsyncSession, payload: dict[str, Any]
) -> None:
    await _notify_payment_event(event_type=EVENT_DOCUMENT_REQUIRED, payload=payload)


@outbox_handler(EVENT_CAPTURED)
async def on_payment_captured_notify(
    _session: AsyncSession, payload: dict[str, Any]
) -> None:
    await _notify_payment_event(event_type=EVENT_CAPTURED, payload=payload)


@outbox_handler(EVENT_REJECTED)
async def on_payment_rejected_notify(
    _session: AsyncSession, payload: dict[str, Any]
) -> None:
    await _notify_payment_event(event_type=EVENT_REJECTED, payload=payload)


@outbox_handler(EVENT_DOCUMENT_INFECTED)
async def on_payment_document_infected_notify(
    _session: AsyncSession, payload: dict[str, Any]
) -> None:
    await _notify_payment_event(event_type=EVENT_DOCUMENT_INFECTED, payload=payload)
