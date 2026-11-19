"""How long conversations are kept, and what the customer's data rights reach
(chantier accueil et messagerie, §7 « Conservation et RGPD »).

- A customer's **resolved** conversation is kept ``messaging_retention_customer_days``
  after its last message (5 years by default), or until ``retain_until`` when the
  customer asked to keep it longer. A notice without content is e-mailed 30 days
  before; the deletion waits for the end of the notice.
- A visitor's conversation (no account) is kept ``messaging_retention_guest_days``
  after its last message (6 months by default), resolved or not, without notice.
- The export holds the customer's conversations and their **messages** only:
  never an internal note, an event or who handled it.
- Erasing an account deletes its conversations: the order and its invoice
  remain the record of a sale.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.datetimes import as_utc, utcnow
from app.core.i18n import resolve_locale
from app.features.messaging.attachments import delete_objects
from app.features.messaging.models import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageKind,
)
from app.features.notification.email_renderer import render_email
from app.features.notification.mailer import queue_email
from app.features.user.crud.user_preference import get_preference_for_user
from app.features.user.models.user import User

NOTICE_BEFORE = datetime.timedelta(days=30)
KEEP_LONGER = datetime.timedelta(days=365)


async def _days(session: AsyncSession, key: str, default: int) -> datetime.timedelta:
    return datetime.timedelta(
        days=int(await runtime_settings.get(key, session) or default)
    )


def deletion_date(
    conversation: Conversation, customer_retention: datetime.timedelta
) -> datetime.datetime | None:
    """When a customer's conversation goes: its last message plus the
    retention, or the date the customer chose if later."""
    last = conversation.last_message_at or conversation.created_at
    if last is None:
        return None
    due = as_utc(last) + customer_retention
    if (
        conversation.retain_until is not None
        and as_utc(conversation.retain_until) > due
    ):
        due = as_utc(conversation.retain_until)
    return due


async def keep_longer(
    session: AsyncSession, conversation: Conversation, *, now: datetime.datetime
) -> datetime.datetime:
    """« Keep one more year »: a year after the current deletion date (or
    now, if later). Cancels a notice already sent."""
    retention = await _days(session, "messaging_retention_customer_days", 1826)
    due = deletion_date(conversation, retention) or now
    conversation.retain_until = max(due, now) + KEEP_LONGER
    conversation.deletion_notice_at = None
    session.add(conversation)
    return conversation.retain_until


async def thread_text(session: AsyncSession, conversation: Conversation) -> str:
    """The conversation as plain text, for the customer to keep: messages
    only, never a note or an event."""
    rows = await session.exec(
        select(ConversationMessage)
        .where(
            col(ConversationMessage.conversation_id) == conversation.id,
            col(ConversationMessage.kind) == MessageKind.MESSAGE.value,
        )
        .order_by(col(ConversationMessage.created_at))
    )
    lines = [f"{conversation.number} — {conversation.subject}", ""]
    for message in rows.all():
        who = "Vous / You" if message.side == "customer" else "Équipe / Team"
        lines += [f"[{as_utc(message.created_at).isoformat()}] {who}", message.body, ""]
    return "\n".join(lines)


async def export_conversations(
    session: AsyncSession, user_id: uuid.UUID
) -> list[dict[str, Any]]:
    """The customer's conversations for the account export."""
    conversations = (
        await session.exec(
            select(Conversation)
            .where(col(Conversation.customer_id) == user_id)
            .order_by(col(Conversation.created_at))
        )
    ).all()
    result: list[dict[str, Any]] = []
    for conversation in conversations:
        messages = (
            await session.exec(
                select(ConversationMessage)
                .where(
                    col(ConversationMessage.conversation_id) == conversation.id,
                    col(ConversationMessage.kind) == MessageKind.MESSAGE.value,
                )
                .order_by(col(ConversationMessage.created_at))
            )
        ).all()
        result.append(
            {
                "number": conversation.number,
                "channel": conversation.channel,
                "topic": conversation.topic,
                "status": conversation.status,
                "subject": conversation.subject,
                "created_at": conversation.created_at.isoformat()
                if conversation.created_at
                else None,
                "messages": [
                    {
                        "side": m.side,
                        "body": m.body,
                        "created_at": as_utc(m.created_at).isoformat(),
                    }
                    for m in messages
                ],
            }
        )
    return result


async def erase_conversations(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Account erasure: the customer's conversations go, files included
    (no commit)."""
    ids = select(Conversation.id).where(col(Conversation.customer_id) == user_id)
    await delete_objects(session, list((await session.exec(ids)).all()))
    await session.execute(
        sa_delete(ConversationMessage).where(
            col(ConversationMessage.conversation_id).in_(ids)
        )
    )
    await session.execute(
        sa_delete(Conversation).where(col(Conversation.customer_id) == user_id)
    )


async def _delete(session: AsyncSession, conversation_ids: list[uuid.UUID]) -> None:
    if not conversation_ids:
        return
    await delete_objects(session, conversation_ids)
    await session.execute(
        sa_delete(ConversationMessage).where(
            col(ConversationMessage.conversation_id).in_(conversation_ids)
        )
    )
    await session.execute(
        sa_delete(Conversation).where(col(Conversation.id).in_(conversation_ids))
    )


async def retention_sweep(
    session: AsyncSession, *, now: datetime.datetime | None = None
) -> dict[str, int]:
    """Notices, then deletions (nightly)."""
    now = now or utcnow()
    customer_retention = await _days(session, "messaging_retention_customer_days", 1826)
    guest_retention = await _days(session, "messaging_retention_guest_days", 183)

    # Visitors: gone after their period, without notice.
    guests = (
        await session.exec(
            select(Conversation.id).where(
                col(Conversation.customer_id).is_(None),
                col(Conversation.last_message_at) <= now - guest_retention,
            )
        )
    ).all()
    await _delete(session, list(guests))

    notices: list[tuple[str, dict[str, Any], str]] = []
    expired: list[uuid.UUID] = []
    resolved = (
        await session.exec(
            select(Conversation).where(
                col(Conversation.customer_id).is_not(None),
                col(Conversation.status) == ConversationStatus.RESOLVED.value,
            )
        )
    ).all()
    for conversation in resolved:
        due = deletion_date(conversation, customer_retention)
        if due is None or due - NOTICE_BEFORE > now:
            continue
        notice = conversation.deletion_notice_at
        # A notice of an earlier cycle (the conversation was reopened and
        # resolved again since) does not count: the customer is told again.
        if notice is not None and as_utc(notice) < due - NOTICE_BEFORE:
            notice = None
        if notice is None:
            conversation.deletion_notice_at = now
            session.add(conversation)
            customer = await session.get(User, conversation.customer_id)
            if customer is None or not customer.is_active or not customer.email:
                continue
            preference = await get_preference_for_user(session, user_id=customer.id)
            notices.append(
                (
                    str(customer.email),
                    {
                        "full_name": customer.full_name or "",
                        "number": conversation.number,
                        "deletion_date": max(due, now + NOTICE_BEFORE)
                        .date()
                        .isoformat(),
                    },
                    resolve_locale(preference.locale if preference else None),
                )
            )
        elif due <= now and as_utc(notice) <= now - NOTICE_BEFORE:
            expired.append(conversation.id)
    await _delete(session, expired)
    # The markers first: the mailer sends on its own transaction.
    await session.commit()
    for recipient, context, lang in notices:
        rendered = render_email("messaging_deletion_notice", lang=lang, **context)
        await queue_email(
            session,
            recipient=recipient,
            subject=rendered.subject,
            text=rendered.text,
            html=rendered.html,
            event_type="messaging.deletion_notice",
        )
    return {"guests": len(guests), "notices": len(notices), "deleted": len(expired)}


__all__ = [
    "deletion_date",
    "erase_conversations",
    "export_conversations",
    "keep_longer",
    "retention_sweep",
    "thread_text",
]
