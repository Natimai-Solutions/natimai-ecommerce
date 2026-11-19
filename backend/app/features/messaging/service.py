"""Messaging rules (chantier accueil et messagerie, §6 and §7).

- A conversation is opened by a customer on a topic; its channel follows.
- Only ``kind = message`` moves a conversation. A customer message on a
  resolved conversation reopens it **without holder** (the holder may be
  away); a team reply never reopens one.
- Taking a conversation is a conditional ``UPDATE`` (two members never hold
  the same one); the first team reply takes it the same way, never over a
  concurrent take. Releasing, resolving or transferring a conversation held
  by someone else needs ``force``: every member is a superuser, so « holder
  or superuser » would exclude nobody.
- Resolving keeps the holder (a free conversation goes to who resolves it):
  a resolved conversation always has someone responsible.
- What a customer can attach a conversation to is checked: their own order,
  quote request or group request, a published product. Anything else reads
  as missing (404).
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func, or_, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.features.cart.models.quote_request import QuoteRequest
from app.features.messaging.models import (
    CHANNEL_TOPICS,
    CHANNELS,
    TOPIC_CHANNEL,
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageKind,
    MessageSide,
    conversation_number_seq,
)
from app.features.order.models.order import Order
from app.features.product.models.product import Product
from app.features.user.models.group_upgrade_request import GroupUpgradeRequest
from app.features.user.models.user import User
from app.features.user.staff import staff_channels

NUMBER_PREFIX = "C"


def not_found(conversation_id: uuid.UUID | str) -> AppError:
    return AppError(
        code="messaging.not_found",
        status_code=404,
        message="Conversation not found.",
        details={"conversation_id": str(conversation_id)},
    )


def display_name(user: User | None) -> str:
    if user is None:
        return ""
    return (user.full_name or "").strip() or str(user.email).split("@")[0]


async def allocate_number(session: AsyncSession, *, now: datetime.datetime) -> str:
    result = await session.execute(conversation_number_seq.next_value().select())
    return f"{NUMBER_PREFIX}-{now.year}-{int(result.scalar_one()):05d}"


def channel_of(topic: str) -> str:
    channel = TOPIC_CHANNEL.get(topic)
    if channel is None:
        raise AppError(
            code="messaging.topic",
            status_code=400,
            message="Unknown topic: {topic}.",
            details={"field": "topic", "topic": topic},
        )
    return channel


async def check_context(
    session: AsyncSession,
    *,
    customer: User | None,
    context_type: str | None,
    context_id: uuid.UUID | None,
) -> None:
    """A customer attaches only what is theirs (or a published product);
    anything else reads as missing — never « forbidden », which would say
    it exists."""
    if context_type is None and context_id is None:
        return
    found = False
    if context_type is not None and context_id is not None:
        if context_type == "product":
            product = await session.get(Product, context_id)
            found = bool(
                product is not None and product.is_active and product.is_admin_active
            )
        elif customer is not None and context_type == "order":
            order = await session.get(Order, context_id)
            found = order is not None and order.user_id == customer.id
        elif customer is not None and context_type == "quote_request":
            quote = await session.get(QuoteRequest, context_id)
            found = quote is not None and quote.user_id == customer.id
        elif customer is not None and context_type == "group_request":
            request = await session.get(GroupUpgradeRequest, context_id)
            found = request is not None and request.user_id == customer.id
    if not found:
        raise AppError(
            code="messaging.context_not_found",
            status_code=404,
            message="What this conversation refers to was not found.",
            details={"field": "context_id"},
        )


def clean_body(body: str) -> str:
    text = (body or "").strip()
    if not text:
        raise AppError(
            code="messaging.empty",
            status_code=400,
            message="The message is empty.",
            details={"field": "body"},
        )
    return text


async def open_conversation(
    session: AsyncSession,
    *,
    topic: str,
    subject: str,
    body: str,
    customer: User | None,
    guest: dict[str, Any] | None = None,
    context_type: str | None = None,
    context_id: uuid.UUID | None = None,
    now: datetime.datetime | None = None,
) -> Conversation:
    """Open a conversation with its first message (no commit)."""
    now = now or utcnow()
    channel = channel_of(topic)
    text = clean_body(body)
    await check_context(
        session, customer=customer, context_type=context_type, context_id=context_id
    )
    conversation = Conversation(
        number=await allocate_number(session, now=now),
        channel=channel,
        topic=topic,
        subject=(subject or "").strip()[:200] or text[:80],
        customer_id=customer.id if customer is not None else None,
        context_type=context_type,
        context_id=context_id,
        created_at=now,
        created_by_id=customer.id if customer is not None else None,
        **(guest or {}),
    )
    session.add(conversation)
    await session.flush()
    await add_message(
        session,
        conversation,
        side=MessageSide.CUSTOMER,
        body=text,
        author_id=conversation.customer_id,
        now=now,
    )
    return conversation


async def add_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    side: MessageSide,
    body: str,
    author_id: uuid.UUID | None,
    kind: MessageKind = MessageKind.MESSAGE,
    data: dict[str, Any] | None = None,
    now: datetime.datetime | None = None,
    with_file: bool = False,
) -> ConversationMessage:
    """Add a message, a note or an event (no commit). Only a message moves
    the conversation. ``with_file``: the text may be empty (a photo alone)."""
    now = now or utcnow()
    text = body if kind == MessageKind.EVENT or with_file else clean_body(body)
    message = ConversationMessage(
        conversation_id=conversation.id,
        author_id=author_id,
        side=side.value,
        kind=kind.value,
        body=(text or "").strip() if with_file else text,
        data=data or {},
        created_at=now,
    )
    session.add(message)
    if kind == MessageKind.MESSAGE:
        conversation.last_message_at = now
        if side == MessageSide.CUSTOMER:
            conversation.last_customer_message_at = now
            conversation.customer_read_at = now
            if conversation.status == ConversationStatus.RESOLVED.value:
                # Reopened: back to the shared queue, the holder may be away.
                conversation.assigned_to_id = None
                conversation.assigned_at = None
                conversation.resolved_at = None
            conversation.status = ConversationStatus.OPEN.value
        else:
            conversation.last_staff_message_at = now
            conversation.staff_read_at = now
            if conversation.first_staff_reply_at is None:
                conversation.first_staff_reply_at = now
            # A team reply never reopens a resolved conversation.
            if conversation.status != ConversationStatus.RESOLVED.value:
                conversation.status = ConversationStatus.PENDING.value
        session.add(conversation)
    await session.flush()
    return message


async def event(
    session: AsyncSession,
    conversation: Conversation,
    *,
    action: str,
    staff: User,
    now: datetime.datetime,
    **data: Any,
) -> None:
    await add_message(
        session,
        conversation,
        side=MessageSide.STAFF,
        body=action,
        author_id=staff.id,
        kind=MessageKind.EVENT,
        data={"action": action, "by": display_name(staff), **data},
        now=now,
    )


async def claim(
    session: AsyncSession,
    conversation: Conversation,
    staff: User,
    *,
    force: bool = False,
    implicit: bool = False,
    now: datetime.datetime | None = None,
) -> bool:
    """Take a conversation. Conditional ``UPDATE``: never over another
    member's take unless ``force``. ``implicit`` (a reply, an upload): free
    conversations only, silently. Returns whether this member holds it."""
    now = now or utcnow()
    if conversation.assigned_to_id == staff.id:
        return True
    conditions: list[Any] = [col(Conversation.id) == conversation.id]
    if implicit or not force:
        conditions.append(col(Conversation.assigned_to_id).is_(None))
    result = await session.execute(
        update(Conversation)
        .where(*conditions)
        .values(assigned_to_id=staff.id, assigned_at=now)
        .returning(col(Conversation.id))
    )
    taken = result.first() is not None
    await session.refresh(conversation)
    if taken:
        await event(session, conversation, action="claimed", staff=staff, now=now)
        return True
    if implicit:
        return False
    holder = (
        await session.get(User, conversation.assigned_to_id)
        if conversation.assigned_to_id
        else None
    )
    raise AppError(
        code="messaging.already_claimed",
        status_code=409,
        message="{holder} already handles this conversation.",
        details={"holder": display_name(holder)},
    )


async def _require_holder_or_force(
    session: AsyncSession, conversation: Conversation, staff: User, force: bool
) -> None:
    if (
        conversation.assigned_to_id is not None
        and conversation.assigned_to_id != staff.id
        and not force
    ):
        holder = await session.get(User, conversation.assigned_to_id)
        raise AppError(
            code="messaging.held_by_other",
            status_code=409,
            message="{holder} handles this conversation: confirm to take over.",
            details={"holder": display_name(holder)},
        )


async def release(
    session: AsyncSession,
    conversation: Conversation,
    staff: User,
    *,
    force: bool = False,
    now: datetime.datetime | None = None,
) -> None:
    now = now or utcnow()
    await _require_holder_or_force(session, conversation, staff, force)
    if conversation.assigned_to_id is None:
        return
    conversation.assigned_to_id = None
    conversation.assigned_at = None
    # Tell the team again: nobody holds it any more.
    conversation.staff_notified_at = None
    session.add(conversation)
    await event(session, conversation, action="released", staff=staff, now=now)


async def resolve_by_staff(
    session: AsyncSession,
    conversation: Conversation,
    staff: User,
    *,
    force: bool = False,
    now: datetime.datetime | None = None,
) -> None:
    now = now or utcnow()
    if conversation.status == ConversationStatus.RESOLVED.value:
        return
    await _require_holder_or_force(session, conversation, staff, force)
    if conversation.assigned_to_id is None:
        conversation.assigned_to_id = staff.id
        conversation.assigned_at = now
    conversation.status = ConversationStatus.RESOLVED.value
    conversation.resolved_at = now
    session.add(conversation)
    await event(session, conversation, action="resolved", staff=staff, now=now)


async def resolve_by_customer(
    session: AsyncSession, conversation: Conversation, *, now: datetime.datetime
) -> None:
    """The customer says it is settled: the holder stays responsible."""
    if conversation.status == ConversationStatus.RESOLVED.value:
        return
    conversation.status = ConversationStatus.RESOLVED.value
    conversation.resolved_at = now
    session.add(conversation)
    await session.flush()


async def transfer(
    session: AsyncSession,
    conversation: Conversation,
    staff: User,
    target_id: uuid.UUID,
    *,
    force: bool = False,
    now: datetime.datetime | None = None,
) -> None:
    now = now or utcnow()
    target = await session.get(User, target_id)
    if (
        target is None
        or not target.is_active
        or conversation.channel not in staff_channels(target)
    ):
        raise AppError(
            code="messaging.invalid_assignee",
            status_code=400,
            message="This person cannot handle conversations.",
            details={"field": "user_id"},
        )
    await _require_holder_or_force(session, conversation, staff, force)
    conversation.assigned_to_id = target.id
    conversation.assigned_at = now
    conversation.staff_notified_at = None
    session.add(conversation)
    await event(
        session,
        conversation,
        action="transferred",
        staff=staff,
        now=now,
        to=display_name(target),
    )


async def change_topic(
    session: AsyncSession,
    conversation: Conversation,
    staff: User,
    *,
    channel: str,
    topic: str,
    now: datetime.datetime | None = None,
) -> None:
    now = now or utcnow()
    if topic not in CHANNEL_TOPICS.get(channel, ()):
        raise AppError(
            code="messaging.topic",
            status_code=400,
            message="Unknown topic: {topic}.",
            details={"field": "topic", "topic": topic},
        )
    if (conversation.channel, conversation.topic) == (channel, topic):
        return
    conversation.channel = channel
    conversation.topic = topic
    session.add(conversation)
    await event(
        session,
        conversation,
        action="moved",
        staff=staff,
        now=now,
        channel=channel,
        topic=topic,
    )
    # Moved to a channel its holder does not work on (lot ROLE): back to the
    # queue of that channel, rather than held by someone who no longer sees
    # it (and still notified of the customer's messages).
    if conversation.assigned_to_id is not None:
        holder = await session.get(User, conversation.assigned_to_id)
        if holder is None or channel not in staff_channels(holder):
            conversation.assigned_to_id = None
            conversation.assigned_at = None
            conversation.staff_notified_at = None
            await event(session, conversation, action="released", staff=staff, now=now)


async def release_out_of_scope(
    session: AsyncSession,
    holder: User,
    staff: User,
    *,
    now: datetime.datetime | None = None,
) -> int:
    """The open conversations ``holder`` holds on channels they no longer
    work on (a role changed or removed, an account deactivated) go back to
    their channel's queue, traced; returns how many (no commit)."""
    now = now or utcnow()
    keeps = set(staff_channels(holder)) if holder.is_active else set()
    held = (
        await session.exec(
            select(Conversation).where(
                col(Conversation.assigned_to_id) == holder.id,
                col(Conversation.status) != ConversationStatus.RESOLVED.value,
            )
        )
    ).all()
    released = 0
    for conversation in held:
        if conversation.channel in keeps:
            continue
        conversation.assigned_to_id = None
        conversation.assigned_at = None
        conversation.staff_notified_at = None
        session.add(conversation)
        await event(session, conversation, action="released", staff=staff, now=now)
        released += 1
    return released


def mark_read(
    conversation: Conversation, side: MessageSide, now: datetime.datetime
) -> None:
    if side == MessageSide.CUSTOMER:
        conversation.customer_read_at = now
    else:
        conversation.staff_read_at = now


def customer_unread_condition() -> Any:
    """A team answer the customer has not read yet."""
    return and_(
        col(Conversation.last_staff_message_at).is_not(None),
        or_(
            col(Conversation.customer_read_at).is_(None),
            col(Conversation.last_staff_message_at)
            > col(Conversation.customer_read_at),
        ),
    )


def staff_unread_condition() -> Any:
    """A customer message the team has not read yet."""
    return and_(
        col(Conversation.last_customer_message_at).is_not(None),
        or_(
            col(Conversation.staff_read_at).is_(None),
            col(Conversation.last_customer_message_at)
            > col(Conversation.staff_read_at),
        ),
    )


async def customer_unread_count(session: AsyncSession, customer_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Conversation)
        .where(
            col(Conversation.customer_id) == customer_id, customer_unread_condition()
        )
    )
    return int(result.scalar_one())


async def thread(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    *,
    staff: bool,
    after: datetime.datetime | None = None,
) -> list[ConversationMessage]:
    """The messages of a conversation, oldest first. A customer never gets a
    note or an event."""
    statement = select(ConversationMessage).where(
        col(ConversationMessage.conversation_id) == conversation_id
    )
    if not staff:
        statement = statement.where(
            col(ConversationMessage.kind) == MessageKind.MESSAGE.value
        )
    if after is not None:
        statement = statement.where(col(ConversationMessage.created_at) > after)
    rows = await session.exec(
        statement.order_by(col(ConversationMessage.created_at).asc())
    )
    return list(rows.all())


@dataclass(frozen=True)
class StaffSummary:
    todo: int
    mine: int
    pending: int
    unread: int


async def staff_summary(
    session: AsyncSession,
    staff_id: uuid.UUID,
    *,
    channels: tuple[str, ...] = CHANNELS,
) -> StaffSummary:
    async def count(*conditions: Any) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(Conversation)
            .where(col(Conversation.channel).in_(channels), *conditions)
        )
        return int(result.scalar_one())

    open_ = col(Conversation.status) == ConversationStatus.OPEN.value
    return StaffSummary(
        todo=await count(open_, col(Conversation.assigned_to_id).is_(None)),
        mine=await count(
            col(Conversation.status) != ConversationStatus.RESOLVED.value,
            col(Conversation.assigned_to_id) == staff_id,
        ),
        pending=await count(
            col(Conversation.status) == ConversationStatus.PENDING.value
        ),
        unread=await count(
            col(Conversation.status) != ConversationStatus.RESOLVED.value,
            staff_unread_condition(),
        ),
    )


__all__ = [
    "StaffSummary",
    "add_message",
    "allocate_number",
    "change_topic",
    "channel_of",
    "check_context",
    "claim",
    "customer_unread_condition",
    "customer_unread_count",
    "display_name",
    "event",
    "mark_read",
    "not_found",
    "open_conversation",
    "release",
    "resolve_by_customer",
    "resolve_by_staff",
    "staff_summary",
    "staff_unread_condition",
    "thread",
    "transfer",
]
