"""Visitors without an account (chantier accueil et messagerie, lot MSG2).

- ``/contact`` opens a conversation for a visitor; **nothing is e-mailed to
  the address typed** (it is not proven: the shop must not become a relay to
  any address). A visitor who writes again on the same address joins their
  conversation still open.
- The first e-mail to the visitor is a **team reply**: it carries the answer
  (the visitor has no other access) and a link « continue on the site ».
  The link is a random token stored as a SHA-256 hash on the conversation,
  valid 30 days, replaced at each reply (one valid link) and used once.
- Following the link proves the address (it was only sent there): signing up
  through it creates a verified account, or signing in with an account of
  this very address, and the visitor's conversations of this address are
  attached to the account.
"""

from __future__ import annotations

import datetime
import secrets
import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.datetimes import as_utc, utcnow
from app.core.errors import AppError
from app.core.i18n import resolve_locale
from app.core.security import hash_reset_token
from app.features.messaging.models import Conversation, ConversationStatus
from app.features.notification.email_renderer import render_email
from app.features.notification.mailer import queue_email

LINK_VALIDITY = datetime.timedelta(days=30)


def continue_url(token: str) -> str:
    return f"{settings.FRONTEND_HOST.rstrip('/')}/contact/suite/{token}"


def invalid_link() -> AppError:
    return AppError(
        code="messaging.link_invalid",
        status_code=404,
        message="This link is no longer valid: write to us again from the contact page.",
        details={},
    )


async def open_guest_conversation_for(
    session: AsyncSession, email: str, *, channel: str
) -> Conversation | None:
    """The visitor's conversation still open on this address and channel,
    about nothing in particular (a quote request has its own thread)."""
    rows = await session.exec(
        select(Conversation)
        .where(
            col(Conversation.customer_id).is_(None),
            col(Conversation.guest_email) == email,
            col(Conversation.channel) == channel,
            col(Conversation.context_type).is_(None),
            col(Conversation.status) != ConversationStatus.RESOLVED.value,
        )
        .order_by(col(Conversation.last_message_at).desc())
        .limit(1)
    )
    return rows.first()


async def email_reply(
    session: AsyncSession,
    conversation: Conversation,
    *,
    body: str,
    with_file: bool,
    now: datetime.datetime | None = None,
) -> None:
    """E-mail a team reply to the visitor, with a fresh link (commits the
    link before the mailer sends: it journals on its own)."""
    if conversation.customer_id is not None or not conversation.guest_email:
        return
    now = now or utcnow()
    token = secrets.token_urlsafe(32)
    conversation.guest_token_hash = hash_reset_token(token)
    conversation.guest_token_expires_at = now + LINK_VALIDITY
    conversation.customer_notified_at = now
    session.add(conversation)
    recipient = conversation.guest_email
    context = {
        "full_name": conversation.guest_name or "",
        "number": conversation.number,
        "reply": body,
        "with_file": with_file,
        "continue_url": continue_url(token),
        "valid_days": LINK_VALIDITY.days,
    }
    lang = resolve_locale(conversation.guest_locale)
    await session.commit()
    rendered = render_email("messaging_guest_reply", lang=lang, **context)
    await queue_email(
        session,
        recipient=recipient,
        subject=rendered.subject,
        text=rendered.text,
        html=rendered.html,
        event_type="messaging.guest_reply",
        # The link is a secret: never re-sent from the e-mail journal.
        resendable=False,
    )


async def conversation_for_token(
    session: AsyncSession, token: str, *, now: datetime.datetime | None = None
) -> Conversation:
    now = now or utcnow()
    if not token or len(token) > 200:
        raise invalid_link()
    row = (
        await session.exec(
            select(Conversation).where(
                col(Conversation.guest_token_hash) == hash_reset_token(token)
            )
        )
    ).first()
    if (
        row is None
        or row.customer_id is not None
        or row.guest_token_expires_at is None
        or as_utc(row.guest_token_expires_at) <= now
    ):
        raise invalid_link()
    return row


async def attach_to_account(
    session: AsyncSession, conversation: Conversation, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """The address is proven: the visitor's conversations of this address
    become the account's; the link is used up (no commit)."""
    email = conversation.guest_email
    rows = (
        await session.exec(
            select(Conversation).where(
                col(Conversation.customer_id).is_(None),
                col(Conversation.guest_email) == email,
            )
        )
    ).all()
    attached: list[uuid.UUID] = []
    for row in rows:
        row.customer_id = user_id
        row.guest_token_hash = None
        row.guest_token_expires_at = None
        session.add(row)
        attached.append(row.id)
    return attached


__all__ = [
    "LINK_VALIDITY",
    "attach_to_account",
    "continue_url",
    "conversation_for_token",
    "email_reply",
    "invalid_link",
    "open_guest_conversation_for",
]
