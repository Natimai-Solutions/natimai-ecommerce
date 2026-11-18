"""E-mails about unread messages, and the automatic release of conversations
held without an answer (chantier accueil et messagerie, §6 « Notifications »).

- A message unread for ``NOTIFY_AFTER`` is notified **once per wave**: a new
  wave is a last message later than both the reader's read marker and the
  last notice. Only conversations active in the last ``ACTIVE_WINDOW`` are
  read; the team is never told about a resolved conversation.
- The customer's e-mail carries no content (only a link to the messages),
  in the customer's language, and stops when they turn the preference off.
- The team's e-mail goes to the holder, else to the channel's address
  (customer service and technical support → ``email_support``, sales →
  ``email_contact``), else to the superusers; in the operator's language.
- The mailer journals and sends on its own transaction: the « notified »
  marker is committed **before** the e-mail is queued, so a failure after it
  never sends the same notice twice.
"""

from __future__ import annotations

import datetime
import html
import logging
from typing import Any

from sqlalchemy import or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.datetimes import utcnow
from app.core.i18n import resolve_locale
from app.core.operator_messages import operator_text
from app.features.messaging.models import (
    Conversation,
    ConversationStatus,
    MessageSide,
)
from app.features.messaging.service import event
from app.features.notification.email_renderer import render_email
from app.features.notification.mailer import queue_email
from app.features.user.crud.user_preference import get_preference_for_user
from app.features.user.models.user import User

logger = logging.getLogger(__name__)

NOTIFY_AFTER = datetime.timedelta(minutes=10)
ACTIVE_WINDOW = datetime.timedelta(days=7)
CHANNEL_ADDRESS = {
    "customer_service": "email_support",
    "technical": "email_support",
    "sales": "email_contact",
}


def messages_url(conversation: Conversation) -> str:
    base = settings.FRONTEND_HOST.rstrip("/")
    return f"{base}/mon-compte?tab=messages&c={conversation.id}"


def admin_url(conversation: Conversation) -> str:
    base = (settings.ADMIN_FRONTEND_HOST or "").rstrip("/")
    return f"{base}/messages/{conversation.id}" if base else ""


async def _customer_due(
    session: AsyncSession, now: datetime.datetime
) -> list[Conversation]:
    staff_at = col(Conversation.last_staff_message_at)
    rows = await session.exec(
        select(Conversation).where(
            col(Conversation.customer_id).is_not(None),
            staff_at.is_not(None),
            staff_at <= now - NOTIFY_AFTER,
            col(Conversation.last_message_at) >= now - ACTIVE_WINDOW,
            or_(
                col(Conversation.customer_read_at).is_(None),
                staff_at > col(Conversation.customer_read_at),
            ),
            or_(
                col(Conversation.customer_notified_at).is_(None),
                staff_at > col(Conversation.customer_notified_at),
            ),
        )
    )
    return list(rows.all())


async def _staff_due(
    session: AsyncSession, now: datetime.datetime
) -> list[Conversation]:
    customer_at = col(Conversation.last_customer_message_at)
    rows = await session.exec(
        select(Conversation).where(
            col(Conversation.status) != ConversationStatus.RESOLVED.value,
            customer_at.is_not(None),
            customer_at <= now - NOTIFY_AFTER,
            col(Conversation.last_message_at) >= now - ACTIVE_WINDOW,
            or_(
                col(Conversation.staff_read_at).is_(None),
                customer_at > col(Conversation.staff_read_at),
            ),
            or_(
                col(Conversation.staff_notified_at).is_(None),
                customer_at > col(Conversation.staff_notified_at),
            ),
        )
    )
    return list(rows.all())


async def _staff_recipients(
    session: AsyncSession, conversation: Conversation
) -> list[str]:
    if conversation.assigned_to_id is not None:
        holder = await session.get(User, conversation.assigned_to_id)
        if holder is not None and holder.is_active and holder.email:
            return [str(holder.email)]
    key = CHANNEL_ADDRESS.get(conversation.channel)
    if key:
        address = str(await runtime_settings.get(key, session) or "").strip()
        if address:
            return [address]
    admins = await session.exec(
        select(User).where(
            col(User.is_superuser).is_(True), col(User.is_active).is_(True)
        )
    )
    return [str(u.email) for u in admins.all() if u.email]


async def notify_unread(
    session: AsyncSession, *, now: datetime.datetime | None = None
) -> dict[str, int]:
    """Queue the e-mails of this wave; returns how many of each were sent."""
    now = now or utcnow()
    to_customers: list[tuple[str, dict[str, Any], str]] = []
    for conversation in await _customer_due(session, now):
        conversation.customer_notified_at = now
        session.add(conversation)
        customer = await session.get(User, conversation.customer_id)
        if customer is None or not customer.is_active or not customer.email:
            continue
        preference = await get_preference_for_user(session, user_id=customer.id)
        if preference is not None and not preference.notification_messages:
            continue
        lang = resolve_locale(preference.locale if preference else None)
        to_customers.append(
            (
                str(customer.email),
                {
                    "full_name": customer.full_name or "",
                    "number": conversation.number,
                    "messages_url": messages_url(conversation),
                },
                lang,
            )
        )

    to_staff: list[tuple[list[str], str, str]] = []
    for conversation in await _staff_due(session, now):
        conversation.staff_notified_at = now
        session.add(conversation)
        recipients = await _staff_recipients(session, conversation)
        if not recipients:
            continue
        values = {
            "number": conversation.number,
            "channel": operator_text(f"messaging.channel.{conversation.channel}"),
            "url": admin_url(conversation) or "—",
        }
        to_staff.append(
            (
                recipients,
                operator_text("messaging.staff_subject", **values),
                operator_text("messaging.staff_body", **values),
            )
        )

    # The markers first: the mailer sends on its own, a rollback after it
    # would notify the same wave again.
    await session.commit()

    for recipient, context, lang in to_customers:
        rendered = render_email("messaging_reply", lang=lang, **context)
        await queue_email(
            session,
            recipient=recipient,
            subject=rendered.subject,
            text=rendered.text,
            html=rendered.html,
            event_type="messaging.reply",
        )
    for recipients, subject, body in to_staff:
        for recipient in recipients:
            await queue_email(
                session,
                recipient=recipient,
                subject=subject,
                text=body,
                html=f"<p>{html.escape(body)}</p>",
                event_type="messaging.staff_waiting",
            )
    return {"customers": len(to_customers), "staff": len(to_staff)}


async def release_stale(
    session: AsyncSession, *, now: datetime.datetime | None = None
) -> int:
    """Give back to the queue the open conversations held for more than N
    days without an answer from their holder since the customer's last
    message. Never a pending or a resolved one."""
    now = now or utcnow()
    days = int(await runtime_settings.get("messaging_release_after_days", session) or 3)
    rows = await session.exec(
        select(Conversation).where(
            col(Conversation.status) == ConversationStatus.OPEN.value,
            col(Conversation.assigned_to_id).is_not(None),
            col(Conversation.assigned_at) <= now - datetime.timedelta(days=days),
            or_(
                col(Conversation.last_staff_message_at).is_(None),
                col(Conversation.last_staff_message_at)
                < col(Conversation.last_customer_message_at),
            ),
        )
    )
    released = 0
    for conversation in rows.all():
        holder = await session.get(User, conversation.assigned_to_id)
        conversation.assigned_to_id = None
        conversation.assigned_at = None
        conversation.staff_notified_at = None
        session.add(conversation)
        if holder is not None:
            await event(
                session,
                conversation,
                action="released_auto",
                staff=holder,
                now=now,
                days=days,
            )
        released += 1
    await session.commit()
    return released


__all__ = ["MessageSide", "messages_url", "notify_unread", "release_stale"]
