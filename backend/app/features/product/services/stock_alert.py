"""« Me prévenir » : subscriptions and the hourly pass that e-mails the
customers whose product is orderable again.

The orderability rule is the storefront's (``utils/availability.ts``):
in stock, a continuous product, or an on-demand product the supplier has.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.features.notification.email_renderer import render_email
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.product.models.product import (
    BACKORDER_MODES,
    AvailabilityMode,
    Product,
)
from app.features.product.models.stock_alert import StockAlert

logger = logging.getLogger(__name__)


def product_orderable(product: Any) -> bool:
    """Same rule as the storefront: stock, or a mode that sells without it."""
    quantity = Decimal(str(getattr(product, "supplier_quantity", None) or 0))
    mode = getattr(product, "availability_mode", None) or AvailabilityMode.STOCK
    mode_value = getattr(mode, "value", mode)
    if mode_value == AvailabilityMode.CONTINUOUS.value:
        return True
    if mode_value in BACKORDER_MODES:
        return quantity > 0
    return quantity > 0


def product_url(product_id: uuid.UUID) -> str:
    return f"{settings.FRONTEND_HOST.rstrip('/')}/produit/{product_id}"


async def subscribe(
    session: AsyncSession,
    *,
    product: Product,
    email: str,
    user_id: uuid.UUID | None,
) -> StockAlert:
    """Register the request (idempotent per product and e-mail); refused on a
    product that can be ordered right now. Flushes, no commit."""
    email = email.strip().lower()
    if product_orderable(product):
        raise AppError(
            code="stock_alert.orderable",
            status_code=409,
            message="Ce produit est disponible : ajoutez-le au panier",
            details={"product_id": str(product.id)},
        )
    existing = (
        await session.exec(
            select(StockAlert).where(
                col(StockAlert.product_id) == product.id,
                col(StockAlert.email) == email,
                col(StockAlert.status) == "pending",
                col(StockAlert.is_active).is_(True),
            )
        )
    ).first()
    if existing is not None:
        return existing
    alert = StockAlert(product_id=product.id, user_id=user_id, email=email)
    session.add(alert)
    await session.flush()
    return alert


async def _send(alert: StockAlert, product: Product) -> bool:
    email = render_email(
        "stock_alert",
        product_name=product.name,
        product_url=product_url(product.id),
        shop_name=getattr(settings, "SHOP_NAME", "Natimai"),
    )
    try:
        provider = get_notification_provider(
            settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
        )
    except UnknownNotificationProviderError:
        provider = get_notification_provider("noop")
    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient=alert.email,
            subject=email.subject,
            text=email.text,
            html=email.html,
            metadata={
                "event_type": "stock_alert.sent",
                "stock_alert_id": str(alert.id),
            },
        )
    )
    return bool(result.delivered)


async def notify_due_alerts(session: AsyncSession) -> dict[str, int]:
    """Cron entry point: e-mail every pending alert whose product is
    orderable again (once), skip the others. Commits."""
    pending = (
        await session.exec(
            select(StockAlert, Product)
            .join(Product, col(Product.id) == col(StockAlert.product_id))
            .where(
                col(StockAlert.status) == "pending",
                col(StockAlert.is_active).is_(True),
            )
        )
    ).all()
    sent = failed = 0
    now = datetime.now(timezone.utc)
    for alert, product in pending:
        if not product.is_active or not product_orderable(product):
            continue
        if await _send(alert, product):
            alert.status = "sent"
            alert.notified_at = now
            session.add(alert)
            sent += 1
        else:
            failed += 1
    await session.commit()
    if failed:
        logger.warning("Stock alerts: %d e-mail(s) failed", failed)
    return {"sent": sent, "failed": failed}


__all__ = ["notify_due_alerts", "product_orderable", "product_url", "subscribe"]
