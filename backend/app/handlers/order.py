"""Handlers pour les événements de commande."""

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.constants import OrderStatusCode
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)


@outbox_handler("change.order.status")
async def handle_order_status_change(session: AsyncSession, payload: dict) -> None:
    """Handler pour les changements de statut de commande"""
    order_id = payload.get("order_id")
    new_status_code = payload.get("new_status_code")
    old_status_code = payload.get("old_status_code")
    user_id = payload.get("user_id")

    logger.info(
        f"Order {order_id} status changed from {old_status_code} to {new_status_code}"
    )

    if new_status_code == OrderStatusCode.PAYMENT_CONFIRMED:
        logger.info(f"Payment confirmed for order {order_id}")

    elif new_status_code == OrderStatusCode.PROCESSING:
        logger.info(f"Order {order_id} is now being processed")

    elif new_status_code == OrderStatusCode.SHIPPED:
        logger.info(f"Order {order_id} has been shipped")

    elif new_status_code == OrderStatusCode.DELIVERED:
        logger.info(f"Order {order_id} has been delivered")

    elif new_status_code == OrderStatusCode.CANCELLED:
        logger.info(f"Order {order_id} has been cancelled")

    elif new_status_code == OrderStatusCode.PAYMENT_FAILED:
        logger.error(f"Payment failed for order {order_id}")


@outbox_handler("create.order")
async def handle_order_created(session: AsyncSession, payload: dict) -> None:
    """Handler pour la création d'une commande"""
    order_id = payload.get("id")
    logger.info(f"New order created: {order_id}")
