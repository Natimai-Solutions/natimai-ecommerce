from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order_status import OrderStatusCreate
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)

ORDER_STATUS_PAID = "Paid"
ORDER_STATUS_PAYMENT_FAILED = "PaymentFailed"
ORDER_STATUS_AWAITING_PAYMENT = "AwaitingPayment"


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
