"""Outbox handlers for order events (customer-facing emails).

Handlers:
- on_order_created    → 'Commande reçue' email after checkout
- on_payment_captured → 'Paiement validé' email to the customer
- on_payment_rejected → 'Paiement échoué' email to the customer
- on_payment_refunded → 'Remboursement effectué' email to the customer

Email bodies live in app/templates/email/<lang>/ and are rendered via
app.features.notification.email_renderer.render_email.

Admin/support technical notifications for payment events are handled
separately in app.features.payment.services.notifications.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.i18n import format_date
from app.features.departure.models import GroupedDeparture
from app.features.invoice.models.credit_note import CreditNote
from app.features.invoice.models.invoice import Invoice
from app.features.notification.email_renderer import render_email
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.order.models.order import Order
from app.features.order.services.order_number import resolve_order_ref
from app.features.order.services.tracking_link import tracking_url_from_payload
from app.features.payment.models.gift_card import GiftCard
from app.features.payment.models.payment import Payment
from app.features.payment.services.deposit import PLAN_DEPOSIT, balance_amount
from app.features.payment.services.gift_cards import (
    EVENT_GIFT_CARDS_ISSUED,
    email_lines,
)
from app.features.user.models.user import User
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)

#: Order status at which the balance of a deposit order is asked for.
BALANCE_TRIGGER_STATUS = "Received"

EVENT_ORDER_CREATED = "order.created"
EVENT_PAYMENT_CAPTURED = "payment.captured"
EVENT_PAYMENT_REJECTED = "payment.rejected"
EVENT_PAYMENT_PARTIALLY_RECEIVED = "payment.partially_received"
EVENT_PAYMENT_REFUNDED = "payment.refunded"
EVENT_INVOICE_ISSUED = "invoice.issued"
EVENT_CREDIT_NOTE_ISSUED = "credit_note.issued"

EVENT_ORDER_STATUS_CHANGED = "order.status_changed"

#: Fulfilment statuses the customer is told about: (title, message). Payment
#: statuses have their own e-mails and are skipped here.
ORDER_STATUS_MESSAGES: dict[str, tuple[str, str]] = {
    "OrderedFromSupplier": (
        "Commandée auprès de notre fournisseur",
        "Votre commande est lancée auprès de notre fournisseur. Nous vous "
        "tiendrons informé(e) à chaque étape jusqu'à sa remise.",
    ),
    "InTransit": (
        "En transit",
        "Votre commande est en route. Nous vous préviendrons à son arrivée.",
    ),
    "AtCustoms": (
        "En douane",
        "Votre commande est arrivée et passe le dédouanement. Cette étape "
        "peut prendre quelques jours.",
    ),
    "Received": (
        "Reçue, contrôle en cours",
        "Nous avons reçu votre commande et la contrôlons. Elle vous sera "
        "remise sous quelques jours.",
    ),
    "ReadyForPickup": (
        "Disponible",
        "Votre commande est disponible : retrait ou livraison selon le mode "
        "choisi à la commande.",
    ),
    "Delivered": (
        "Livrée",
        "Votre commande a été remise. Nous espérons qu'elle vous donne entière "
        "satisfaction.",
    ),
    "Backordered": (
        "Article en rupture",
        "Un article de votre commande est en rupture chez notre fournisseur. "
        "Nous revenons vers vous pour un report sur le prochain départ, une "
        "substitution ou un remboursement.",
    ),
    "Cancelled": (
        "Annulée",
        "Votre commande a été annulée. Si un paiement avait été encaissé, il "
        "vous est remboursé.",
    ),
}


async def _email_lang(session: AsyncSession, payload: dict[str, Any]) -> str:
    """Language of a customer e-mail: the order's (frozen at checkout), else
    the customer's saved preference, else the shop's default (R7 / L3)."""
    from app.core.i18n import resolve_locale, user_locale

    order_locale = None
    raw = payload.get("order_id")
    if raw:
        try:
            order = await session.get(Order, uuid.UUID(str(raw)))
        except (TypeError, ValueError):
            order = None
        order_locale = getattr(order, "locale", None) if order else None
    if order_locale:
        return resolve_locale(order_locale)
    return resolve_locale(await user_locale(session, payload.get("user_id")))


#: The same messages in English (R7 / L3).
ORDER_STATUS_MESSAGES_EN: dict[str, tuple[str, str]] = {
    "OrderedFromSupplier": (
        "Ordered from our supplier",
        "Your order has been placed with our supplier. We will keep you "
        "informed at every step until it is handed over.",
    ),
    "InTransit": (
        "In transit",
        "Your order is on its way. We will let you know when it arrives.",
    ),
    "AtCustoms": (
        "At customs",
        "Your order has arrived and is going through customs. This step can "
        "take a few days.",
    ),
    "Received": (
        "Received, being checked",
        "We have received your order and are checking it. It will be handed "
        "over within a few days.",
    ),
    "ReadyForPickup": (
        "Available",
        "Your order is available: pickup or delivery depending on the mode "
        "chosen at checkout.",
    ),
    "Delivered": (
        "Delivered",
        "Your order has been handed over. We hope you are fully satisfied with it.",
    ),
    "Backordered": (
        "Item out of stock",
        "An item of your order is out of stock at our supplier. We will get "
        "back to you with a postponement to the next departure, a substitute "
        "or a refund.",
    ),
    "Cancelled": (
        "Cancelled",
        "Your order has been cancelled. If a payment was collected, it is "
        "refunded to you.",
    ),
}


def _shop_name() -> str:
    return str(runtime_settings.peek("shop_name"))


async def _send_order_email(
    session: AsyncSession,
    *,
    user_id_raw: str | None,
    subject: str,
    text: str,
    html: str,
    event_type: str,
    payload: dict[str, Any],
    recipient: str | None = None,
) -> bool:
    """Resolve user email and dispatch the notification if enabled.

    ``recipient`` names the address directly when there is no account behind
    the message (a visitor's cart reminder, R8 / U9).

    Returns whether the message actually reached the provider, so a caller
    that must not lose the notification (the invoice) can fail and be retried.
    """
    if not await runtime_settings.get("notifications_email_enabled", session):
        return False

    user_uuid: uuid.UUID | str = recipient or ""
    if recipient is None:
        if not user_id_raw:
            logger.warning("order email: missing user_id in payload, skipping")
            return False

        try:
            user_uuid = uuid.UUID(str(user_id_raw))
        except (TypeError, ValueError):
            logger.warning("order email: invalid user_id %r, skipping", user_id_raw)
            return False

        user = await session.get(User, user_uuid)
        if user is None or not user.email:
            logger.warning("order email: user %s not found or has no email", user_uuid)
            return False
        recipient = user.email

    try:
        provider = get_notification_provider(
            settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
        )
    except UnknownNotificationProviderError:
        # Unreachable now that the setting is a Literal validated at startup.
        # If it ever fires, say so loudly: noop throws the e-mail away.
        logger.error(
            "Unknown notification provider '%s' — e-mail discarded",
            settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER,
        )
        return False

    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient=recipient,
            subject=subject,
            text=text,
            html=html,
            metadata={"event_type": event_type, "payload": payload},
        )
    )
    if not result.delivered:
        logger.warning(
            "order email failed: event=%s user=%s provider=%s error=%s",
            event_type,
            user_uuid,
            result.provider_code,
            result.error,
        )
    return bool(result.delivered)


async def _resolve_user_from_payload(
    session: AsyncSession, payload: dict[str, Any]
) -> User | None:
    raw = payload.get("user_id")
    if not raw:
        return None
    try:
        return await session.get(User, uuid.UUID(str(raw)))
    except (TypeError, ValueError):
        return None


# Customer-facing order reference (M5) — shared with the shipping handlers.
_resolve_order_ref = resolve_order_ref


async def _load_payment_and_order(
    session: AsyncSession, payload: dict[str, Any]
) -> tuple[Payment | None, Order | None]:
    """The payment and order named by a payment payload, when loadable."""
    payment: Payment | None = None
    order: Order | None = None
    try:
        if payload.get("payment_id"):
            payment = await session.get(Payment, uuid.UUID(str(payload["payment_id"])))
        if payload.get("order_id"):
            order = await session.get(Order, uuid.UUID(str(payload["order_id"])))
    except (TypeError, ValueError):
        return None, None
    return (
        payment if isinstance(payment, Payment) else None,
        order if isinstance(order, Order) else None,
    )


def _order_pay_url(order_id: uuid.UUID) -> str:
    return f"{settings.FRONTEND_HOST.rstrip('/')}/mon-compte/commandes/{order_id}/solde"


async def request_balance(session: AsyncSession, order: Order) -> bool:
    """Ask the customer for the balance of a deposit order: e-mail with the
    amounts and the payment link, ``balance_requested_at`` stamped. Sent
    again on every call (the admin's « renvoyer » button). Flushes, no commit.
    Returns whether the e-mail reached the provider."""
    user = await session.get(User, order.user_id)
    full_name = (user.full_name or user.email or "") if user else ""
    currency = order.currency or settings.REFERENCE_CURRENCY
    email = render_email(
        "balance_due",
        lang=await _email_lang(
            session, {"order_id": str(order.id), "user_id": str(order.user_id)}
        ),
        full_name=full_name or "client",
        order_id=str(order.id),
        order_ref=order.order_number or "",
        total_amount=str(order.total_amount),
        deposit_amount=str(order.deposit_amount),
        balance_amount=str(balance_amount(order)),
        currency=currency,
        pay_url=_order_pay_url(order.id),
        shop_name=_shop_name(),
    )
    order.balance_requested_at = datetime.now(UTC)
    session.add(order)
    await session.flush()
    return await _send_order_email(
        session,
        user_id_raw=str(order.user_id),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type="order.balance_due",
        payload={"order_id": str(order.id), "order_number": order.order_number},
    )


@outbox_handler(EVENT_ORDER_STATUS_CHANGED)
async def on_order_received_request_balance(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """When the goods are received, a deposit order is asked for its balance
    (once — the admin can re-send it from the order page)."""
    if str(payload.get("new_status") or "") != BALANCE_TRIGGER_STATUS:
        return
    try:
        order = await session.get(Order, uuid.UUID(str(payload.get("order_id"))))
    except (TypeError, ValueError):
        return
    if not isinstance(order, Order) or order.payment_plan != PLAN_DEPOSIT:
        return
    if order.balance_paid_at is not None or order.balance_requested_at is not None:
        return
    await request_balance(session, order)
    await session.commit()


@outbox_handler(EVENT_ORDER_CREATED)
async def on_order_created(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Send 'Commande reçue' email to the customer after checkout."""
    logger.info(
        "Order created: order_id=%s user_id=%s",
        payload.get("order_id"),
        payload.get("user_id"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "order_created",
        lang=await _email_lang(session, payload),
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        total_amount=payload.get("total_amount", ""),
        currency=payload.get("currency", ""),
        item_count=payload.get("item_count", ""),
        tracking_url=tracking_url_from_payload(payload.get("order_id")),
        amount_due_now=payload.get("amount_due_now") or "",
        payment_instructions=payload.get("payment_instructions") or "",
        shop_name=_shop_name(),
    )

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_ORDER_CREATED,
        payload=payload,
    )


@outbox_handler(EVENT_PAYMENT_CAPTURED)
async def on_payment_captured_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send 'Paiement validé' HTML email to the customer."""
    if payload.get("provider_code") == "store_credit":
        # Spending an avoir is not a payment the customer made: the money
        # payment (if any) carries the e-mail, the order e-mail the rest.
        return
    logger.info(
        "Payment captured (customer email): order_id=%s user_id=%s",
        payload.get("order_id"),
        payload.get("user_id"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    order_ref = await _resolve_order_ref(session, payload)

    # A deposit or a balance gets its own wording (and the balance left).
    payment, order = await _load_payment_and_order(session, payload)
    kind = getattr(payment, "kind", None)
    kind = kind if isinstance(kind, str) else "full"
    email = render_email(
        "payment_captured",
        lang=await _email_lang(session, payload),
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        total_amount=payload.get("total_amount", ""),
        currency=payload.get("currency", ""),
        payment_kind=kind,
        balance_amount=str(balance_amount(order)) if order is not None else "",
        shop_name=_shop_name(),
    )

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_PAYMENT_CAPTURED,
        payload=payload,
    )


@outbox_handler(EVENT_PAYMENT_PARTIALLY_RECEIVED)
async def on_payment_partially_received_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send « Versement reçu, reste X » after an instalment (R3-P2)."""
    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""
    email = render_email(
        "payment_received_partial",
        lang=await _email_lang(session, payload),
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=await _resolve_order_ref(session, payload),
        amount=payload.get("amount", ""),
        received_amount=payload.get("received_amount", ""),
        remaining_amount=payload.get("remaining_amount", ""),
        currency=payload.get("currency", ""),
        tracking_url=tracking_url_from_payload(payload.get("order_id")),
        shop_name=_shop_name(),
    )
    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_PAYMENT_PARTIALLY_RECEIVED,
        payload=payload,
    )


@outbox_handler(EVENT_PAYMENT_REJECTED)
async def on_payment_rejected_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send 'Paiement échoué' HTML email to the customer."""
    logger.info(
        "Payment rejected (customer email): order_id=%s user_id=%s reason=%s",
        payload.get("order_id"),
        payload.get("user_id"),
        payload.get("reason"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "payment_rejected",
        lang=await _email_lang(session, payload),
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        reason=payload.get("reason") or "",
        shop_name=_shop_name(),
    )

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_PAYMENT_REJECTED,
        payload=payload,
    )


@outbox_handler(EVENT_PAYMENT_REFUNDED)
async def on_payment_refunded_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send a 'Remboursement effectué' email to the customer."""
    logger.info(
        "Payment refunded (customer email): order_id=%s user_id=%s amount=%s",
        payload.get("order_id"),
        payload.get("user_id"),
        payload.get("amount"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "payment_refunded",
        lang=await _email_lang(session, payload),
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        amount=payload.get("amount", ""),
        currency=payload.get("currency", ""),
        reason=payload.get("reason") or "",
        fully_refunded=bool(payload.get("fully_refunded")),
        shop_name=_shop_name(),
    )

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_PAYMENT_REFUNDED,
        payload=payload,
    )


@outbox_handler(EVENT_INVOICE_ISSUED)
async def on_invoice_issued_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Deliver the issued invoice to the customer.

    The invoice was created and stored but never sent: the customer had to
    guess it existed and go and fetch it. The e-mail carries the numbers and a
    link to the account page rather than the PDF itself — rendering it needs
    WeasyPrint's system libraries, and a missing font must not cost the
    customer the notice that they have been invoiced.

    ``Invoice.emailed_at`` makes this idempotent: the outbox guarantees
    at-least-once delivery, so without it a replay would mail the same invoice
    again.
    """
    raw_invoice_id = payload.get("invoice_id")
    if not raw_invoice_id:
        logger.warning("invoice email: missing invoice_id in payload, skipping")
        return
    try:
        invoice_id = uuid.UUID(str(raw_invoice_id))
    except (TypeError, ValueError):
        logger.warning("invoice email: invalid invoice_id %r", raw_invoice_id)
        return

    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        logger.warning("invoice email: invoice %s not found", invoice_id)
        return
    if invoice.emailed_at is not None:
        logger.info(
            "Invoice %s already e-mailed at %s — skipping replay",
            invoice.invoice_number,
            invoice.emailed_at,
        )
        return

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""
    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "invoice_issued",
        lang=await _email_lang(session, payload),
        full_name=full_name or "client",
        invoice_number=invoice.invoice_number,
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        total_incl_tax=payload.get("total_incl_tax", ""),
        total_tax=payload.get("total_tax", ""),
        currency=payload.get("currency", ""),
        invoice_url=f"{settings.FRONTEND_HOST.rstrip('/')}/mon-compte",
        shop_name=_shop_name(),
    )

    delivered = await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_INVOICE_ISSUED,
        payload=payload,
    )
    if not delivered:
        # Leave emailed_at unset so the ARQ retry tries again.
        raise RuntimeError(f"Invoice {invoice.invoice_number} e-mail was not delivered")

    invoice.emailed_at = datetime.now(UTC)
    session.add(invoice)
    await session.commit()


@outbox_handler(EVENT_GIFT_CARDS_ISSUED)
async def on_gift_cards_issued_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send the buyer the codes of the gift cards their paid order contains.

    The codes exist only in this message and in the admin's list: a failed
    delivery raises so the outbox retries it.
    """
    card_ids: list[uuid.UUID] = []
    for raw in payload.get("card_ids") or []:
        try:
            card_ids.append(uuid.UUID(str(raw)))
        except (TypeError, ValueError):
            continue
    if not card_ids:
        logger.warning("gift card email: no card ids in payload, skipping")
        return
    from sqlmodel import col, select

    cards = list(
        (
            await session.exec(
                select(GiftCard)
                .where(col(GiftCard.id).in_(card_ids))
                .order_by(col(GiftCard.code))
            )
        ).all()
    )
    if not cards:
        logger.warning("gift card email: cards %s not found", card_ids)
        return

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""
    order_ref = await _resolve_order_ref(session, payload)
    email = render_email(
        "gift_card_issued",
        lang=await _email_lang(session, payload),
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        cards=email_lines(cards),
        account_url=f"{settings.FRONTEND_HOST.rstrip('/')}/mon-compte",
        shop_name=_shop_name(),
    )
    delivered = await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_GIFT_CARDS_ISSUED,
        payload=payload,
    )
    if not delivered and await runtime_settings.get(
        "notifications_email_enabled", session
    ):
        raise RuntimeError(f"Gift card e-mail for order {order_ref} was not delivered")


@outbox_handler(EVENT_CREDIT_NOTE_ISSUED)
async def on_credit_note_issued_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Deliver the credit note that corrects an invoice (Z2).

    Same contract as the invoice mail: numbers and a link to the account page
    rather than the PDF, ``CreditNote.emailed_at`` for idempotence, and a
    failed delivery raises so the outbox retries.
    """
    raw_id = payload.get("credit_note_id")
    if not raw_id:
        logger.warning("credit note email: missing credit_note_id, skipping")
        return
    try:
        credit_note_id = uuid.UUID(str(raw_id))
    except (TypeError, ValueError):
        logger.warning("credit note email: invalid credit_note_id %r", raw_id)
        return

    credit_note = await session.get(CreditNote, credit_note_id)
    if credit_note is None:
        logger.warning("credit note email: credit note %s not found", credit_note_id)
        return
    if credit_note.emailed_at is not None:
        logger.info(
            "Credit note %s already e-mailed at %s — skipping replay",
            credit_note.credit_note_number,
            credit_note.emailed_at,
        )
        return

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""
    order_ref = await _resolve_order_ref(session, payload)
    snapshot: dict[str, Any] = getattr(credit_note, "snapshot", None) or {}
    invoice_number = (snapshot.get("invoice") or {}).get("number") or ""

    email = render_email(
        "credit_note_issued",
        lang=await _email_lang(session, payload),
        full_name=full_name or "client",
        credit_note_number=credit_note.credit_note_number,
        invoice_number=invoice_number,
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        total_incl_tax=payload.get("total_incl_tax", ""),
        total_tax=payload.get("total_tax", ""),
        currency=payload.get("currency", ""),
        reason=payload.get("reason", "") or credit_note.reason or "",
        account_url=f"{settings.FRONTEND_HOST.rstrip('/')}/mon-compte",
        shop_name=_shop_name(),
    )

    delivered = await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_CREDIT_NOTE_ISSUED,
        payload=payload,
    )
    if not delivered:
        raise RuntimeError(
            f"Credit note {credit_note.credit_note_number} e-mail was not delivered"
        )

    credit_note.emailed_at = datetime.now(UTC)
    session.add(credit_note)
    await session.commit()


@outbox_handler(EVENT_ORDER_STATUS_CHANGED)
async def on_order_status_changed_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Tell the customer about a fulfilment step (one template, one message
    per status). Payment statuses are covered by their own handlers."""
    new_status = str(payload.get("new_status") or "")
    if new_status not in ORDER_STATUS_MESSAGES:
        logger.debug("order.status_changed %s: no customer message", new_status)
        return
    lang = await _email_lang(session, payload)
    messages = ORDER_STATUS_MESSAGES_EN if lang == "en" else ORDER_STATUS_MESSAGES
    title, body = messages[new_status]

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    departure_name: str | None = None
    estimated_delivery: str | None = None
    raw_departure = payload.get("grouped_departure_id")
    if raw_departure:
        try:
            departure = await session.get(
                GroupedDeparture, uuid.UUID(str(raw_departure))
            )
        except (TypeError, ValueError):
            departure = None
        if departure is not None:
            departure_name = departure.name
            if departure.estimated_delivery_at:
                estimated_delivery = format_date(departure.estimated_delivery_at, lang)

    email = render_email(
        "order_status_changed",
        lang=lang,
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=payload.get("order_number") or "",
        status_title=title,
        status_message=body,
        departure_name=departure_name,
        estimated_delivery=estimated_delivery,
        tracking_url=tracking_url_from_payload(payload.get("order_id")),
        shop_name=_shop_name(),
    )
    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_ORDER_STATUS_CHANGED,
        payload=payload,
    )
