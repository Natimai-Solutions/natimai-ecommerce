"""Quote requests and price-group requests in the messaging (chantier
accueil et messagerie, lot MSG5).

- A quote request opens a sales conversation (topic ``quote``) attached to
  it: the customer gets an acknowledgement where the answer will come, and
  can write about it. The request keeps its own life (statuses, the
  ``EMAIL_FAILED`` safety net, issuing, acceptance): the conversation is
  attached, it replaces nothing.
- Issuing a quote posts a team message in the conversation (the quote itself
  is e-mailed as before: no second notice).
- The quote's ``admin_comment`` stays internal: written in the conversation as
  an internal note.
- A price-group request opens a sales conversation (topic ``price_group``):
  the team asks there for a proof, the customer sends it as a file. The
  decision is posted as a team message (it stands for the decision e-mail
  that did not exist); ``admin_comment`` is the reason shown to the customer.

Nothing here runs while the messaging module is off. The texts a customer
reads are in the customer's language.
"""

from __future__ import annotations

import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.datetimes import utcnow
from app.core.i18n import request_locale, resolve_locale
from app.core.operator_messages import operator_locale
from app.features.cart.models.quote_request import QuoteRequest
from app.features.messaging import service
from app.features.messaging.models import Conversation, MessageKind, MessageSide
from app.features.system.modules import module_enabled
from app.features.user.crud.user_preference import get_preference_for_user
from app.features.user.models.group_upgrade_request import GroupUpgradeRequest
from app.features.user.models.user import User

_TEXTS: dict[str, tuple[str, str]] = {
    # (English, French)
    "quote.subject": ("Quote request", "Demande de devis"),
    "quote.body": (
        "Quote request sent from my cart ({count} item(s)).",
        "Demande de devis envoyée depuis mon panier ({count} article(s)).",
    ),
    "quote.issued": (
        "Your quote {number} is ready: you will find it in My account → Quotes, "
        "where you can order it until {valid_until}.",
        "Votre devis {number} est prêt : retrouvez-le dans Mon compte → Devis, "
        "où vous pouvez le commander jusqu'au {valid_until}.",
    ),
    "quote.issued_guest": (
        "Your quote {number} is ready: it is valid until {valid_until}. "
        "Reply here for any question about it.",
        "Votre devis {number} est prêt : il est valable jusqu'au {valid_until}. "
        "Répondez ici pour toute question à son sujet.",
    ),
    "quote.note": ("Quote comment: {comment}", "Commentaire du devis : {comment}"),
    "group.subject": ("Price group « {group} »", "Groupe tarifaire « {group} »"),
    "group.body": (
        "I would like to join the price group « {group} ».",
        "Je souhaite rejoindre le groupe tarifaire « {group} ».",
    ),
    "group.registration": (
        "Registration number: {value}",
        "N° d'immatriculation : {value}",
    ),
    "group.approved": (
        "Your request is accepted: your account is now in the price group « {group} ».",
        "Votre demande est acceptée : votre compte est désormais dans le groupe « {group} ».",
    ),
    "group.rejected": (
        "Your request to join the price group « {group} » is declined.",
        "Votre demande de passage dans le groupe « {group} » n'est pas acceptée.",
    ),
}


def text(key: str, lang: str, **values: object) -> str:
    english, french = _TEXTS[key]
    return (french if lang == "fr" else english).format(**values)


async def _customer_lang(session: AsyncSession, user_id: uuid.UUID | None) -> str:
    preference = (
        await get_preference_for_user(session, user_id=user_id) if user_id else None
    )
    return resolve_locale(preference.locale if preference else None, request_locale())


async def conversation_about(
    session: AsyncSession, context_type: str, context_id: uuid.UUID
) -> Conversation | None:
    rows = await session.exec(
        select(Conversation)
        .where(
            col(Conversation.context_type) == context_type,
            col(Conversation.context_id) == context_id,
        )
        .order_by(col(Conversation.created_at))
        .limit(1)
    )
    return rows.first()


async def open_for_quote(
    session: AsyncSession, quote: QuoteRequest, *, customer: User | None
) -> Conversation | None:
    """The conversation of a new quote request (no commit)."""
    if not await module_enabled(session, "messaging"):
        return None
    lang = await _customer_lang(session, customer.id if customer else None)
    count = len((quote.items_snapshot or {}).get("items") or [])
    body = (quote.notes or "").strip() or text("quote.body", lang, count=count)
    guest = None
    if customer is None:
        guest = {
            "guest_name": quote.full_name,
            "guest_email": (quote.email or "").strip().lower() or None,
            "guest_phone": quote.phone,
            "guest_locale": lang,
        }
    conversation = await service.open_conversation(
        session,
        topic="quote",
        subject=text("quote.subject", lang),
        body=body,
        customer=customer,
        guest=guest,
    )
    # Attached here, not through ``check_context``: the request was just made.
    conversation.context_type = "quote_request"
    conversation.context_id = quote.id
    session.add(conversation)
    return conversation


async def quote_issued(
    session: AsyncSession,
    quote: QuoteRequest,
    *,
    staff: User,
    emailed: bool = True,
) -> None:
    """Post « your quote is ready » in the quote's conversation (no commit).
    When the quote goes by e-mail (``emailed``), that e-mail tells the
    customer: no second notice; otherwise the usual « a reply is waiting »
    notice goes."""
    if not await module_enabled(session, "messaging"):
        return
    conversation = await conversation_about(session, "quote_request", quote.id)
    if conversation is None or not quote.quote_number:
        return
    lang = (
        await _customer_lang(session, conversation.customer_id)
        if conversation.customer_id
        else resolve_locale(conversation.guest_locale)
    )
    now = utcnow()
    valid_until = quote.valid_until.strftime("%d/%m/%Y") if quote.valid_until else "—"
    await service.claim(session, conversation, staff, implicit=True, now=now)
    await service.add_message(
        session,
        conversation,
        side=MessageSide.STAFF,
        # A visitor has no « My account »: the quote itself is in the e-mail.
        body=text(
            "quote.issued" if conversation.customer_id else "quote.issued_guest",
            lang,
            number=quote.quote_number,
            valid_until=valid_until,
        ),
        author_id=staff.id,
        now=now,
    )
    if emailed:
        conversation.customer_notified_at = now
        session.add(conversation)


async def quote_email_not_sent(session: AsyncSession, quote: QuoteRequest) -> None:
    """The quote e-mail did not leave: the « a reply is waiting » notice is
    owed again (no commit)."""
    conversation = await conversation_about(session, "quote_request", quote.id)
    if conversation is not None and conversation.customer_notified_at is not None:
        conversation.customer_notified_at = None
        session.add(conversation)


async def notify_guest_of_quote(session: AsyncSession, quote: QuoteRequest) -> None:
    """A visitor's quote went without its e-mail (not asked, or failed): the
    « your quote is ready » message reaches the visitor by e-mail, with the
    link to continue — a visitor has no account where the notice would wait
    (commits)."""
    from app.features.messaging import guests
    from app.features.messaging.models import ConversationMessage as Message

    conversation = await conversation_about(session, "quote_request", quote.id)
    if (
        conversation is None
        or conversation.customer_id is not None
        or conversation.customer_notified_at is not None
    ):
        return
    last = (
        await session.exec(
            select(Message)
            .where(
                col(Message.conversation_id) == conversation.id,
                col(Message.side) == MessageSide.STAFF.value,
                col(Message.kind) == MessageKind.MESSAGE.value,
            )
            .order_by(col(Message.created_at).desc())
            .limit(1)
        )
    ).first()
    if last is None:
        return
    await guests.email_reply(session, conversation, body=last.body, with_file=False)


async def quote_commented(
    session: AsyncSession, quote: QuoteRequest, *, staff: User, comment: str
) -> None:
    """The quote's internal comment, written as an internal note (no commit)."""
    if not await module_enabled(session, "messaging"):
        return
    conversation = await conversation_about(session, "quote_request", quote.id)
    if conversation is None or not comment.strip():
        return
    await service.add_message(
        session,
        conversation,
        side=MessageSide.STAFF,
        body=text("quote.note", operator_locale(), comment=comment),
        author_id=staff.id,
        kind=MessageKind.NOTE,
    )


async def open_for_group_request(
    session: AsyncSession,
    request: GroupUpgradeRequest,
    *,
    customer: User,
    group_label: str,
) -> Conversation | None:
    """The conversation of a new price-group request (no commit)."""
    if not await module_enabled(session, "messaging"):
        return None
    lang = await _customer_lang(session, customer.id)
    lines = [text("group.body", lang, group=group_label)]
    if request.business_registration_number:
        lines.append(
            text("group.registration", lang, value=request.business_registration_number)
        )
    if request.attestation_notes:
        lines.append(request.attestation_notes)
    conversation = await service.open_conversation(
        session,
        topic="price_group",
        subject=text("group.subject", lang, group=group_label),
        body="\n".join(lines),
        customer=customer,
    )
    conversation.context_type = "group_request"
    conversation.context_id = request.id
    session.add(conversation)
    return conversation


async def group_decided(
    session: AsyncSession,
    request: GroupUpgradeRequest,
    *,
    staff: User,
    approved: bool,
    group_label: str,
    comment: str | None,
) -> None:
    """Post the decision in the request's conversation (no commit): the
    customer is told by the usual « a reply is waiting » e-mail."""
    if not await module_enabled(session, "messaging"):
        return
    conversation = await conversation_about(session, "group_request", request.id)
    if conversation is None:
        return
    lang = await _customer_lang(session, conversation.customer_id)
    body = text(
        "group.approved" if approved else "group.rejected", lang, group=group_label
    )
    if comment and comment.strip():
        body = f"{body}\n\n{comment.strip()}"
    now = utcnow()
    await service.claim(session, conversation, staff, implicit=True, now=now)
    await service.add_message(
        session,
        conversation,
        side=MessageSide.STAFF,
        body=body,
        author_id=staff.id,
        now=now,
    )


__all__ = [
    "conversation_about",
    "group_decided",
    "open_for_group_request",
    "open_for_quote",
    "quote_commented",
    "notify_guest_of_quote",
    "quote_email_not_sent",
    "quote_issued",
    "text",
]
