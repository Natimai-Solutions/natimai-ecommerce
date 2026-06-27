"""Deferred-capture orchestration: capture a previously AUTHORISED card payment.

When ``PAYZEN_MANUAL_VALIDATION`` is on, CB payments are only authorised at
checkout (status ``Authorized``). This service performs the actual debit
(provider ``capture()``), then lands the payment on the normal ``Completed``
status and publishes ``payment.captured`` — reusing the existing downstream
(order status, supplier order, customer email).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment
from app.features.payment.providers import get_provider
from app.features.payment.providers.base import PaymentProviderError
from app.features.user.models.user import User
from app.outbox.registry import outbox_registry

PAYMENT_STATUS_AUTHORIZED = "Authorized"
PAYMENT_STATUS_CAPTURED = "Completed"
EVENT_PAYMENT_CAPTURED = "payment.captured"


@dataclass(slots=True)
class CaptureOutcome:
    """Result of a capture request returned to the API layer."""

    payment: Payment
    message: str | None


def _provider_trans_uuid(payment: Payment) -> str | None:
    data = payment.provider_data or {}
    raw = data.get("trans_uuid") or data.get("trans_id")
    return str(raw) if raw else None


async def capture_payment(
    session: AsyncSession, *, payment: Payment, admin: User
) -> CaptureOutcome:
    """Capture an authorised payment (trigger the actual card debit)."""
    # Capture plain values before any commit (which expires the ORM instances).
    payment_id = payment.id
    order_id = payment.order_id
    user_id = payment.user_id
    currency = payment.currency
    amount = payment.amount
    provider_code = payment.provider_code
    current_status_id = payment.payment_status_id
    admin_id = admin.id
    trans_uuid = _provider_trans_uuid(payment)

    authorized = await crud_payment_status.get_by_name(
        session, name=PAYMENT_STATUS_AUTHORIZED
    )
    if authorized is None or current_status_id != authorized.id:
        raise AppError(
            code="capture.not_authorized",
            status_code=400,
            message="Le paiement n'est pas en attente de capture (statut « Authorized »).",
            details={"payment_id": str(payment_id)},
        )
    if not trans_uuid:
        raise AppError(
            code="capture.no_transaction",
            status_code=400,
            message="Transaction du prestataire introuvable pour la capture.",
            details={"payment_id": str(payment_id)},
        )

    try:
        provider = get_provider(provider_code)
    except PaymentProviderError as exc:
        raise AppError(
            code="capture.provider_unknown",
            status_code=400,
            message=f"Fournisseur de paiement inconnu : {provider_code}",
            details={"provider_code": provider_code},
        ) from exc

    result = await provider.capture(
        payment_reference=trans_uuid, amount=amount, currency=currency
    )
    if result.status != "completed":
        raise AppError(
            code="capture.failed",
            status_code=502,
            message=result.message or "Capture refusée par le prestataire.",
        )

    captured = await crud_payment_status.get_by_name(
        session, name=PAYMENT_STATUS_CAPTURED
    )
    if captured is not None:
        payment.payment_status_id = captured.id
        session.add(payment)

    await outbox_registry.publish(
        session=session,
        event_type=EVENT_PAYMENT_CAPTURED,
        payload={
            "payment_id": str(payment_id),
            "order_id": str(order_id) if order_id else None,
            "user_id": str(user_id) if user_id else None,
            "provider_code": provider_code,
            "total_amount": str(amount),
            "currency": currency,
            "action": "capture",
            "admin_user_id": str(admin_id),
            "metadata": {"trans_uuid": trans_uuid},
        },
        correlation_id=payment_id,
    )

    await session.commit()
    await session.refresh(payment)
    return CaptureOutcome(payment=payment, message=result.message)
