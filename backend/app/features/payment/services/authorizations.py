"""Life of a card authorisation that is not captured at checkout (R8 / confort).

With ``PAYZEN_MANUAL_VALIDATION`` the card is only *authorised* at checkout
(payment status ``Authorized``) and the debit happens later. Three things
must then happen without an admin remembering them:

* **auto-capture** when the order reaches the fulfilment step chosen in
  ``payment_auto_capture_status`` (default: ``InTransit``, the shipment);
* **void** of the authorisation when the order is cancelled
  (``payment_void_on_cancel``): the customer's bank releases the hold;
* an **alert** before an authorisation expires unused: a card authorisation
  holds about a week (``payment_authorization_validity_days``, default 7);
  the daily sweep warns the ops webhook the day before, once per payment,
  and the dashboard counts the payments still to capture.

Everything here is best effort towards the provider: a refused capture or
void is logged and alerted, never raised into the order's status change.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.alerting import send_alert
from app.core.errors import AppError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
)
from app.features.payment.providers import get_provider
from app.features.payment.providers.base import PaymentProviderError
from app.features.payment.services.capture_service import (
    PAYMENT_STATUS_AUTHORIZED,
    capture_payment,
)
from app.features.system import audit

logger = logging.getLogger(__name__)

#: Payment status of a released authorisation (seeded by initial_data).
PAYMENT_STATUS_VOIDED = "Voided"
ORDER_STATUS_CANCELLED = "Cancelled"

SETTING_AUTO_CAPTURE_STATUS = "payment_auto_capture_status"
SETTING_VOID_ON_CANCEL = "payment_void_on_cancel"
SETTING_VALIDITY_DAYS = "payment_authorization_validity_days"

#: Key kept in ``provider_data`` once the expiry alert went out.
EXPIRY_ALERTED_KEY = "authorization_expiry_alerted_at"


async def authorized_payments_of_order(
    session: AsyncSession, order_id: uuid.UUID
) -> list[Payment]:
    """The order's payments still waiting for their capture."""
    rows = await crud_payment.list_with_status_by_order_id(session, order_id=order_id)
    return [
        payment
        for payment, status_name in rows
        if status_name == PAYMENT_STATUS_AUTHORIZED and payment.is_active
    ]


async def capture_on_status(
    session: AsyncSession, *, order_id: uuid.UUID, new_status: str
) -> int:
    """Capture the order's authorised payments if ``new_status`` is the step
    configured for the automatic capture. Returns how many were captured."""
    target = str(await runtime_settings.get(SETTING_AUTO_CAPTURE_STATUS, session) or "")
    if not target or new_status != target:
        return 0
    captured = 0
    for payment in await authorized_payments_of_order(session, order_id):
        payment_id = payment.id
        try:
            await capture_payment(session, payment=payment, admin=None)
            captured += 1
            logger.info(
                "Payment %s captured automatically (order %s reached %s)",
                payment_id,
                order_id,
                new_status,
            )
        except AppError as exc:
            logger.error(
                "Automatic capture of payment %s failed: %s", payment_id, exc.message
            )
            await send_alert(
                f"Capture automatique refusée pour le paiement {payment_id} "
                f"(commande {order_id}) : {exc.message}. À capturer à la main.",
                source="payments",
            )
    return captured


async def _voided_status(session: AsyncSession) -> PaymentStatus:
    status = await crud_payment_status.get_by_name(session, name=PAYMENT_STATUS_VOIDED)
    if status is not None:
        return status
    created = await crud_payment_status.create_draft(
        session=session,
        data=PaymentStatusCreate(
            name=PAYMENT_STATUS_VOIDED,
            description="Card authorisation released, never captured",
        ),
        user=None,
    )
    await session.flush()
    return created


async def void_on_cancel(session: AsyncSession, *, order_id: uuid.UUID) -> int:
    """Release the authorisations of a cancelled order. Returns how many."""
    if not bool(await runtime_settings.get(SETTING_VOID_ON_CANCEL, session)):
        return 0
    voided = 0
    for payment in await authorized_payments_of_order(session, order_id):
        payment_id = payment.id
        amount, currency, provider_code = (
            payment.amount,
            payment.currency,
            payment.provider_code,
        )
        provider_data = dict(payment.provider_data or {})
        try:
            provider = get_provider(provider_code)
            reference = provider.capture_reference(provider_data)
            if not reference:
                raise PaymentProviderError("transaction reference missing")
            result = await provider.void(
                payment_reference=reference, amount=amount, currency=currency
            )
            if result.status != "completed":
                raise PaymentProviderError(result.message or "void refused")
        except (PaymentProviderError, AppError) as exc:
            message = getattr(exc, "message", None) or str(exc)
            logger.error("Void of payment %s failed: %s", payment_id, message)
            await send_alert(
                f"Annulation d'autorisation refusée pour le paiement {payment_id} "
                f"(commande {order_id} annulée) : {message}. À libérer chez le "
                "prestataire.",
                source="payments",
            )
            continue
        status = await _voided_status(session)
        payment.payment_status_id = status.id
        provider_data["voided_at"] = datetime.now(UTC).isoformat()
        payment.provider_data = provider_data
        session.add(payment)
        await session.commit()
        await audit.record(
            event="payment.voided",
            details={"payment_id": str(payment_id), "order_id": str(order_id)},
            session=session,
        )
        voided += 1
        logger.info("Payment %s voided (order %s cancelled)", payment_id, order_id)
    return voided


async def expiring_authorizations(
    session: AsyncSession, *, now: datetime, validity_days: int, warn_days: int = 1
) -> list[Payment]:
    """Authorised payments that expire within ``warn_days`` (oldest first)."""
    threshold = now - timedelta(days=max(validity_days - warn_days, 0))
    statement = (
        select(Payment)
        .join(PaymentStatus, col(PaymentStatus.id) == col(Payment.payment_status_id))
        .where(
            col(PaymentStatus.name) == PAYMENT_STATUS_AUTHORIZED,
            col(Payment.is_active).is_(True),
            col(Payment.created_at) <= threshold,
        )
        .order_by(col(Payment.created_at))
    )
    return list((await session.exec(statement)).all())


async def alert_expiring_authorizations(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Daily sweep: one ops alert per authorisation about to expire unused."""
    current = now or datetime.now(UTC)
    validity = int(await runtime_settings.get(SETTING_VALIDITY_DAYS, session))
    if validity <= 0:
        return {"disabled": 1, "alerted": 0, "expiring": 0}
    payments = await expiring_authorizations(
        session, now=current, validity_days=validity
    )
    alerted = 0
    for payment in payments:
        data: dict[str, Any] = dict(payment.provider_data or {})
        if data.get(EXPIRY_ALERTED_KEY):
            continue
        created = payment.created_at
        age_days = (
            (current - created.replace(tzinfo=created.tzinfo or UTC)).days
            if created
            else 0
        )
        await send_alert(
            f"Autorisation carte de {payment.amount} {payment.currency} "
            f"(paiement {payment.id}, commande {payment.order_id}) autorisée il y a "
            f"{age_days} j : elle expire sous {validity} j sans capture. "
            "Capturer depuis Paiements, ou annuler la commande pour la libérer.",
            source="payments",
        )
        data[EXPIRY_ALERTED_KEY] = current.isoformat()
        payment.provider_data = data
        session.add(payment)
        await session.commit()
        alerted += 1
    return {"alerted": alerted, "expiring": len(payments)}


__all__ = [
    "EXPIRY_ALERTED_KEY",
    "ORDER_STATUS_CANCELLED",
    "PAYMENT_STATUS_VOIDED",
    "SETTING_AUTO_CAPTURE_STATUS",
    "SETTING_VALIDITY_DAYS",
    "SETTING_VOID_ON_CANCEL",
    "alert_expiring_authorizations",
    "authorized_payments_of_order",
    "capture_on_status",
    "expiring_authorizations",
    "void_on_cancel",
]
