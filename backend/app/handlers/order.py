"""Outbox handlers for order events (customer-facing emails).

Handlers:
- on_order_created    → 'Commande reçue' email after checkout
- on_payment_captured → 'Paiement validé' email to the customer
- on_payment_rejected → 'Paiement échoué' email to the customer

Admin/support technical notifications for payment events are handled
separately in app.features.payment.services.notifications.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from jinja2 import Template
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.user.models.user import User
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)

EVENT_ORDER_CREATED = "order.created"

_TEXT_ORDER_CREATED = """\
Bonjour {{ full_name }},

Votre commande a bien été enregistrée.

Numéro de commande : {{ order_id }}
Montant total      : {{ total_amount }} {{ currency }}
Nombre d'articles  : {{ item_count }}

Vous recevrez une confirmation dès que votre paiement aura été validé.

Merci pour votre commande,
L'équipe {{ shop_name }}
"""

_HTML_ORDER_CREATED = """\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Commande reçue</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }
    .wrapper { max-width: 600px; margin: 32px auto; background: #ffffff; border-radius: 8px; overflow: hidden; }
    .header { background: #1a3c5e; padding: 24px 32px; }
    .header h1 { color: #ffffff; margin: 0; font-size: 20px; }
    .body { padding: 32px; color: #333333; }
    .body p { margin: 0 0 16px; line-height: 1.5; }
    .summary { background: #f0f4f8; border-radius: 6px; padding: 16px 24px; margin: 24px 0; }
    .summary table { width: 100%; border-collapse: collapse; }
    .summary td { padding: 6px 0; font-size: 14px; }
    .summary td:first-child { color: #666666; width: 55%; }
    .summary td:last-child { font-weight: bold; text-align: right; }
    .footer { padding: 16px 32px; background: #f0f4f8; font-size: 12px; color: #888888; text-align: center; }
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <h1>Commande enregistrée</h1>
    </div>
    <div class="body">
      <p>Bonjour {{ full_name }},</p>
      <p>Votre commande a bien été enregistrée. Vous recevrez une confirmation dès que votre paiement aura été validé.</p>
      <div class="summary">
        <table>
          <tr><td>Numéro de commande</td><td>{{ order_id }}</td></tr>
          <tr><td>Montant total</td><td>{{ total_amount }} {{ currency }}</td></tr>
          <tr><td>Nombre d'articles</td><td>{{ item_count }}</td></tr>
        </table>
      </div>
      <p>Merci pour votre commande,<br><strong>L'équipe {{ shop_name }}</strong></p>
    </div>
    <div class="footer">Ce message est envoyé automatiquement, merci de ne pas y répondre.</div>
  </div>
</body>
</html>
"""

_tpl_text = Template(_TEXT_ORDER_CREATED)
_tpl_html = Template(_HTML_ORDER_CREATED)


async def _send_order_email(
    session: AsyncSession,
    *,
    user_id_raw: str | None,
    subject: str,
    text: str,
    html: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Resolve user email and dispatch the notification if enabled."""
    if not settings.PAYMENT_NOTIFICATIONS_EMAIL_ENABLED:
        return

    if not user_id_raw:
        logger.warning("order email: missing user_id in payload, skipping")
        return

    try:
        user_uuid = uuid.UUID(str(user_id_raw))
    except (TypeError, ValueError):
        logger.warning("order email: invalid user_id %r, skipping", user_id_raw)
        return

    user = await session.get(User, user_uuid)
    if user is None or not user.email:
        logger.warning("order email: user %s not found or has no email", user_uuid)
        return

    try:
        provider = get_notification_provider(
            settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
        )
    except UnknownNotificationProviderError:
        provider = get_notification_provider("noop")

    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient=user.email,
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


EVENT_PAYMENT_CAPTURED = "payment.captured"
EVENT_PAYMENT_REJECTED = "payment.rejected"

_TEXT_PAYMENT_CAPTURED = """\
Bonjour {{ full_name }},

Votre paiement a été validé pour la commande {{ order_id }}.

Montant débité : {{ total_amount }} {{ currency }}

Votre commande est maintenant en cours de traitement.

Merci pour votre confiance,
L'équipe {{ shop_name }}
"""

_HTML_PAYMENT_CAPTURED = """\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Paiement validé</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }
    .wrapper { max-width: 600px; margin: 32px auto; background: #ffffff; border-radius: 8px; overflow: hidden; }
    .header { background: #1a7a4a; padding: 24px 32px; }
    .header h1 { color: #ffffff; margin: 0; font-size: 20px; }
    .body { padding: 32px; color: #333333; }
    .body p { margin: 0 0 16px; line-height: 1.5; }
    .badge { display: inline-block; background: #e6f4ed; color: #1a7a4a; border-radius: 4px; padding: 4px 12px; font-weight: bold; margin-bottom: 16px; }
    .summary { background: #f0f4f8; border-radius: 6px; padding: 16px 24px; margin: 24px 0; }
    .summary table { width: 100%; border-collapse: collapse; }
    .summary td { padding: 6px 0; font-size: 14px; }
    .summary td:first-child { color: #666666; width: 55%; }
    .summary td:last-child { font-weight: bold; text-align: right; }
    .footer { padding: 16px 32px; background: #f0f4f8; font-size: 12px; color: #888888; text-align: center; }
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header"><h1>Paiement validé ✓</h1></div>
    <div class="body">
      <p>Bonjour {{ full_name }},</p>
      <span class="badge">Paiement confirmé</span>
      <p>Votre paiement a bien été reçu. Votre commande est maintenant en cours de traitement.</p>
      <div class="summary">
        <table>
          <tr><td>Numéro de commande</td><td>{{ order_id }}</td></tr>
          <tr><td>Montant débité</td><td>{{ total_amount }} {{ currency }}</td></tr>
        </table>
      </div>
      <p>Merci pour votre confiance,<br><strong>L'équipe {{ shop_name }}</strong></p>
    </div>
    <div class="footer">Ce message est envoyé automatiquement, merci de ne pas y répondre.</div>
  </div>
</body>
</html>
"""

_TEXT_PAYMENT_REJECTED = """\
Bonjour {{ full_name }},

Votre paiement pour la commande {{ order_id }} n'a pas pu être traité.

{{ reason_line }}

Veuillez réessayer ou contacter notre support si le problème persiste.

L'équipe {{ shop_name }}
"""

_HTML_PAYMENT_REJECTED = """\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Paiement échoué</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }
    .wrapper { max-width: 600px; margin: 32px auto; background: #ffffff; border-radius: 8px; overflow: hidden; }
    .header { background: #7a1a1a; padding: 24px 32px; }
    .header h1 { color: #ffffff; margin: 0; font-size: 20px; }
    .body { padding: 32px; color: #333333; }
    .body p { margin: 0 0 16px; line-height: 1.5; }
    .badge { display: inline-block; background: #fdecea; color: #7a1a1a; border-radius: 4px; padding: 4px 12px; font-weight: bold; margin-bottom: 16px; }
    .reason { background: #fdecea; border-left: 4px solid #7a1a1a; border-radius: 4px; padding: 12px 16px; margin: 16px 0; font-size: 14px; }
    .summary { background: #f0f4f8; border-radius: 6px; padding: 16px 24px; margin: 24px 0; }
    .summary table { width: 100%; border-collapse: collapse; }
    .summary td { padding: 6px 0; font-size: 14px; }
    .summary td:first-child { color: #666666; width: 55%; }
    .footer { padding: 16px 32px; background: #f0f4f8; font-size: 12px; color: #888888; text-align: center; }
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header"><h1>Paiement non abouti</h1></div>
    <div class="body">
      <p>Bonjour {{ full_name }},</p>
      <span class="badge">Paiement refusé</span>
      <p>Malheureusement, votre paiement pour la commande <strong>{{ order_id }}</strong> n'a pas pu être traité.</p>
      {% if reason %}<div class="reason">{{ reason }}</div>{% endif %}
      <p>Veuillez réessayer ou contacter notre support si le problème persiste.</p>
      <p>L'équipe {{ shop_name }}</p>
    </div>
    <div class="footer">Ce message est envoyé automatiquement, merci de ne pas y répondre.</div>
  </div>
</body>
</html>
"""

_tpl_text_captured = Template(_TEXT_PAYMENT_CAPTURED)
_tpl_html_captured = Template(_HTML_PAYMENT_CAPTURED)
_tpl_text_rejected = Template(_TEXT_PAYMENT_REJECTED)
_tpl_html_rejected = Template(_HTML_PAYMENT_REJECTED)


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

    ctx = {
        "full_name": full_name or "client",
        "order_id": payload.get("order_id", ""),
        "total_amount": payload.get("total_amount", ""),
        "currency": payload.get("currency", ""),
        "item_count": payload.get("item_count", ""),
        "shop_name": getattr(settings, "SHOP_NAME", "Natimai"),
    }
    text, html = _tpl_text.render(**ctx), _tpl_html.render(**ctx)
    order_id = payload.get("order_id", "")

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=f"Votre commande {order_id} a été enregistrée",
        text=text,
        html=html,
        event_type=EVENT_ORDER_CREATED,
        payload=payload,
    )


@outbox_handler(EVENT_PAYMENT_CAPTURED)
async def on_payment_captured_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send 'Paiement validé' HTML email to the customer."""
    logger.info(
        "Payment captured (customer email): order_id=%s user_id=%s",
        payload.get("order_id"),
        payload.get("user_id"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    ctx = {
        "full_name": full_name or "client",
        "order_id": payload.get("order_id", ""),
        "total_amount": payload.get("total_amount", ""),
        "currency": payload.get("currency", ""),
        "shop_name": getattr(settings, "SHOP_NAME", "Natimai"),
    }
    text = _tpl_text_captured.render(**ctx)
    html = _tpl_html_captured.render(**ctx)
    order_id = payload.get("order_id", "")

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=f"Votre paiement pour la commande {order_id} a été validé",
        text=text,
        html=html,
        event_type=EVENT_PAYMENT_CAPTURED,
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
    reason = payload.get("reason") or ""

    ctx = {
        "full_name": full_name or "client",
        "order_id": payload.get("order_id", ""),
        "reason": reason,
        "reason_line": f"Motif : {reason}" if reason else "",
        "shop_name": getattr(settings, "SHOP_NAME", "Natimai"),
    }
    text = _tpl_text_rejected.render(**ctx)
    html = _tpl_html_rejected.render(**ctx)
    order_id = payload.get("order_id", "")

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=f"Problème avec votre paiement — commande {order_id}",
        text=text,
        html=html,
        event_type=EVENT_PAYMENT_REJECTED,
        payload=payload,
    )
