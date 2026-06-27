"""Outbox handlers for shipping / tracking events (customer-facing emails).

Handlers:
- on_tracking_status_changed → email for 'shipped' and 'delivered' milestones
  Respects user.preference.notification_shipping_steps.
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
from app.features.order.models.order import Order
from app.features.user.crud.user_preference import get_preference_for_user
from app.features.user.models.user import User
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)

_SHIPPED_CODES = {"shipped", "expedie", "en_transit", "in_transit"}
_DELIVERED_CODES = {"delivered", "livre", "livré", "delivered_to_customer"}

_TEXT_SHIPPED = """\
Bonjour {{ full_name }},

Bonne nouvelle : votre commande {{ order_id }} est en route !

{% if tracking_ref %}Référence de suivi : {{ tracking_ref }}
{% endif %}{% if estimated_delivery %}Livraison estimée : {{ estimated_delivery }}
{% endif %}
Vous pouvez suivre l'avancement de votre livraison dans votre espace client.

L'équipe {{ shop_name }}
"""

_HTML_SHIPPED = """\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Commande expédiée</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }
    .wrapper { max-width: 600px; margin: 32px auto; background: #ffffff; border-radius: 8px; overflow: hidden; }
    .header { background: #1a5e9e; padding: 24px 32px; }
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
    <div class="header"><h1>Votre commande est expédiée 🚚</h1></div>
    <div class="body">
      <p>Bonjour {{ full_name }},</p>
      <p>Bonne nouvelle ! Votre commande <strong>{{ order_id }}</strong> est maintenant en route.</p>
      <div class="summary">
        <table>
          {% if tracking_ref %}<tr><td>Référence de suivi</td><td>{{ tracking_ref }}</td></tr>{% endif %}
          {% if estimated_delivery %}<tr><td>Livraison estimée</td><td>{{ estimated_delivery }}</td></tr>{% endif %}
        </table>
      </div>
      <p>L'équipe {{ shop_name }}</p>
    </div>
    <div class="footer">Ce message est envoyé automatiquement, merci de ne pas y répondre.</div>
  </div>
</body>
</html>
"""

_TEXT_DELIVERED = """\
Bonjour {{ full_name }},

Votre commande {{ order_id }} a été livrée.

Nous espérons que vous êtes satisfait(e) de votre achat. N'hésitez pas à nous contacter si vous avez la moindre question.

L'équipe {{ shop_name }}
"""

_HTML_DELIVERED = """\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Commande livrée</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }
    .wrapper { max-width: 600px; margin: 32px auto; background: #ffffff; border-radius: 8px; overflow: hidden; }
    .header { background: #1a7a4a; padding: 24px 32px; }
    .header h1 { color: #ffffff; margin: 0; font-size: 20px; }
    .body { padding: 32px; color: #333333; }
    .body p { margin: 0 0 16px; line-height: 1.5; }
    .footer { padding: 16px 32px; background: #f0f4f8; font-size: 12px; color: #888888; text-align: center; }
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header"><h1>Commande livrée ✓</h1></div>
    <div class="body">
      <p>Bonjour {{ full_name }},</p>
      <p>Votre commande <strong>{{ order_id }}</strong> a bien été livrée. Nous espérons que vous êtes satisfait(e) de votre achat.</p>
      <p>L'équipe {{ shop_name }}</p>
    </div>
    <div class="footer">Ce message est envoyé automatiquement, merci de ne pas y répondre.</div>
  </div>
</body>
</html>
"""

_PROGRESS_CODES = {"in_progress", "en_cours"}

_TEXT_PROGRESS = """\
Bonjour {{ full_name }},

Votre commande {{ order_id }} progresse : elle vient de passer à l'étape de transport suivante.

{% if tracking_ref %}Référence de suivi : {{ tracking_ref }}
{% endif %}Vous pouvez suivre l'avancement de votre livraison dans votre espace client.

L'équipe {{ shop_name }}
"""

_HTML_PROGRESS = """\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Votre commande progresse</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }
    .wrapper { max-width: 600px; margin: 32px auto; background: #ffffff; border-radius: 8px; overflow: hidden; }
    .header { background: #3949ab; padding: 24px 32px; }
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
    <div class="header"><h1>Votre colis progresse 📦</h1></div>
    <div class="body">
      <p>Bonjour {{ full_name }},</p>
      <p>Votre commande <strong>{{ order_id }}</strong> vient de passer à l'étape de transport suivante.</p>
      <div class="summary">
        <table>
          {% if tracking_ref %}<tr><td>Référence de suivi</td><td>{{ tracking_ref }}</td></tr>{% endif %}
        </table>
      </div>
      <p>L'équipe {{ shop_name }}</p>
    </div>
    <div class="footer">Ce message est envoyé automatiquement, merci de ne pas y répondre.</div>
  </div>
</body>
</html>
"""

_tpl_text_shipped = Template(_TEXT_SHIPPED)
_tpl_html_shipped = Template(_HTML_SHIPPED)
_tpl_text_delivered = Template(_TEXT_DELIVERED)
_tpl_html_delivered = Template(_HTML_DELIVERED)
_tpl_text_progress = Template(_TEXT_PROGRESS)
_tpl_html_progress = Template(_HTML_PROGRESS)


async def _resolve_order_user(
    session: AsyncSession, order_id_raw: str | None
) -> User | None:
    """Return the User associated with an order."""
    if not order_id_raw:
        return None
    try:
        oid = uuid.UUID(str(order_id_raw))
    except (TypeError, ValueError):
        return None

    order = await session.get(Order, oid)
    if order is None or order.user_id is None:
        return None
    return await session.get(User, order.user_id)


async def _send_shipping_email(
    session: AsyncSession,
    *,
    user: User,
    subject: str,
    text: str,
    html: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Check notification preference and send the email if enabled."""
    if not settings.PAYMENT_NOTIFICATIONS_EMAIL_ENABLED:
        return

    pref = await get_preference_for_user(session, user_id=user.id)
    if pref is not None and not pref.notification_shipping_steps:
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
            "shipping email failed: event=%s user=%s provider=%s error=%s",
            event_type,
            user.id,
            result.provider_code,
            result.error,
        )


@outbox_handler("tracking.status_changed")
async def on_tracking_status_changed(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send shipping notification email on progress/shipped/delivered milestones."""
    status_code = (payload.get("status_code") or "").strip().lower()
    order_id_raw = payload.get("order_id")
    tracking_ref = payload.get("tracking_ref")
    estimated_delivery = payload.get("estimated_delivery")

    if (
        status_code not in _SHIPPED_CODES
        and status_code not in _DELIVERED_CODES
        and status_code not in _PROGRESS_CODES
    ):
        return

    user = await _resolve_order_user(session, order_id_raw)
    if user is None or not user.email:
        logger.warning(
            "tracking email: could not resolve user for order %s", order_id_raw
        )
        return

    full_name = user.full_name or user.email or ""
    shop_name = getattr(settings, "SHOP_NAME", "Natimai")
    order_id_display = str(order_id_raw or "")

    if status_code in _SHIPPED_CODES:
        ctx = {
            "full_name": full_name or "client",
            "order_id": order_id_display,
            "tracking_ref": tracking_ref or "",
            "estimated_delivery": estimated_delivery or "",
            "shop_name": shop_name,
        }
        text = _tpl_text_shipped.render(**ctx)
        html = _tpl_html_shipped.render(**ctx)
        subject = f"Votre commande {order_id_display} est expédiée"
        event_label = "tracking.shipped"
    elif status_code in _DELIVERED_CODES:
        ctx = {
            "full_name": full_name or "client",
            "order_id": order_id_display,
            "shop_name": shop_name,
        }
        text = _tpl_text_delivered.render(**ctx)
        html = _tpl_html_delivered.render(**ctx)
        subject = f"Votre commande {order_id_display} a été livrée"
        event_label = "tracking.delivered"
    else:  # progress milestone (next-leg activation)
        ctx = {
            "full_name": full_name or "client",
            "order_id": order_id_display,
            "tracking_ref": tracking_ref or "",
            "shop_name": shop_name,
        }
        text = _tpl_text_progress.render(**ctx)
        html = _tpl_html_progress.render(**ctx)
        subject = f"Votre commande {order_id_display} progresse"
        event_label = "tracking.progress"

    await _send_shipping_email(
        session,
        user=user,
        subject=subject,
        text=text,
        html=html,
        event_type=event_label,
        payload=payload,
    )
