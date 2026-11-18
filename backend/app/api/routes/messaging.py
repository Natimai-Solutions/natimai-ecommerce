"""Messaging, customer side (chantier accueil et messagerie, lot MSG1).

``GET /messaging/info`` is public: channels and topics, opening hours, the
response time shown, the contact address. The ``/me/conversations`` routes
belong to the signed-in customer: a conversation of someone else reads as
missing (404), and a customer never gets an internal note or an event.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep, module_required
from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.core.rate_limit import hit_rate_limit
from app.features.messaging import service
from app.features.messaging.info import public_info
from app.features.messaging.models import (
    BODY_MAX,
    CONTEXT_TYPES,
    SUBJECT_MAX,
    Conversation,
    ConversationMessage,
    MessageSide,
)
from app.features.user.models.user import User

router = APIRouter(
    tags=["messaging"], dependencies=[Depends(module_required("messaging"))]
)


class ResponseTime(BaseModel):
    unit: str
    value: int
    measured: bool


class ChannelTopics(BaseModel):
    channel: str
    topics: list[str]


class MessagingInfo(BaseModel):
    channels: list[ChannelTopics]
    hours_start: str
    hours_end: str
    #: ISO weekdays (1 = Monday).
    days: list[int]
    timezone: str
    response_time: ResponseTime
    contact_email: str | None = None


class MessagePublic(BaseModel):
    """A message as the customer sees it."""

    id: uuid.UUID
    side: str
    body: str
    created_at: datetime.datetime
    #: Name of the team member who wrote it (customer side: empty).
    author_name: str = ""


class ConversationSummary(BaseModel):
    id: uuid.UUID
    number: str
    channel: str
    topic: str
    status: str
    subject: str
    context_type: str | None = None
    context_id: uuid.UUID | None = None
    created_at: datetime.datetime | None = None
    last_message_at: datetime.datetime | None = None
    unread: bool = False


class ConversationDetail(ConversationSummary):
    messages: list[MessagePublic] = []


class ConversationCreate(BaseModel):
    topic: str = Field(max_length=30)
    subject: str = Field(default="", max_length=SUBJECT_MAX)
    body: str = Field(min_length=1, max_length=BODY_MAX)
    context_type: str | None = Field(default=None, max_length=30)
    context_id: uuid.UUID | None = None


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=BODY_MAX)


class UnreadCount(BaseModel):
    count: int


def _summary(conversation: Conversation) -> ConversationSummary:
    staff_at = conversation.last_staff_message_at
    read_at = conversation.customer_read_at
    return ConversationSummary(
        id=conversation.id,
        number=conversation.number,
        channel=conversation.channel,
        topic=conversation.topic,
        status=conversation.status,
        subject=conversation.subject,
        context_type=conversation.context_type,
        context_id=conversation.context_id,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
        unread=bool(staff_at and (read_at is None or staff_at > read_at)),
    )


async def _authors(
    session: SessionDep, messages: list[ConversationMessage]
) -> dict[uuid.UUID, str]:
    ids = {
        m.author_id
        for m in messages
        if m.author_id and m.side == MessageSide.STAFF.value
    }
    names: dict[uuid.UUID, str] = {}
    for author_id in ids:
        names[author_id] = service.display_name(await session.get(User, author_id))
    return names


async def customer_messages(
    session: SessionDep, messages: list[ConversationMessage]
) -> list[MessagePublic]:
    names = await _authors(session, messages)
    return [
        MessagePublic(
            id=m.id,
            side=m.side,
            body=m.body,
            created_at=m.created_at,
            author_name=names.get(m.author_id, "") if m.author_id else "",
        )
        for m in messages
    ]


async def _own(
    session: SessionDep, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.customer_id != user_id:
        raise service.not_found(conversation_id)
    return conversation


async def _limit(key: str, *, limit: int, window_seconds: int) -> None:
    if await hit_rate_limit(key, limit=limit, window_seconds=window_seconds):
        raise AppError(
            code="messaging.rate_limited",
            status_code=429,
            message="Too many messages: try again in a few minutes.",
            details={"window_seconds": window_seconds},
        )


@router.get("/messaging/info", response_model=MessagingInfo)
async def messaging_info(session: SessionDep) -> MessagingInfo:
    """Channels and topics, opening hours, response time, contact address."""
    return MessagingInfo.model_validate(await public_info(session))


@router.get("/me/conversations", response_model=list[ConversationSummary])
async def list_my_conversations(
    session: SessionDep, current_user: CurrentUser
) -> list[ConversationSummary]:
    """The customer's conversations, most recent activity first."""
    rows = await session.exec(
        select(Conversation)
        .where(col(Conversation.customer_id) == current_user.id)
        .order_by(col(Conversation.last_message_at).desc().nulls_last())
        .limit(200)
    )
    return [_summary(c) for c in rows.all()]


@router.get("/me/conversations/unread", response_model=UnreadCount)
async def my_unread_count(
    session: SessionDep, current_user: CurrentUser
) -> UnreadCount:
    """How many conversations hold an answer the customer has not read."""
    return UnreadCount(
        count=await service.customer_unread_count(session, current_user.id)
    )


@router.post("/me/conversations", response_model=ConversationDetail, status_code=201)
async def open_my_conversation(
    body: ConversationCreate, session: SessionDep, current_user: CurrentUser
) -> ConversationDetail:
    """Open a conversation on a topic (the channel follows), optionally about
    the customer's order, quote request, group request or a product."""
    if body.context_type is not None and body.context_type not in CONTEXT_TYPES:
        raise AppError(
            code="messaging.context_not_found",
            status_code=404,
            message="What this conversation refers to was not found.",
            details={"field": "context_id"},
        )
    await _limit(f"msg-open:{current_user.id}", limit=10, window_seconds=3600)
    conversation = await service.open_conversation(
        session,
        topic=body.topic,
        subject=body.subject,
        body=body.body,
        customer=current_user,
        context_type=body.context_type,
        context_id=body.context_id,
    )
    conversation_id, user_id = conversation.id, current_user.id
    await session.commit()
    return await _detail(session, conversation_id, user_id)


@router.get("/me/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_my_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    after: Annotated[datetime.datetime | None, Query()] = None,
) -> ConversationDetail:
    """A conversation and its messages (only those after ``after`` when
    given: the open thread polls with it)."""
    return await _detail(session, conversation_id, current_user.id, after=after)


async def _detail(
    session: SessionDep,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    after: datetime.datetime | None = None,
) -> ConversationDetail:
    conversation = await _own(session, conversation_id, user_id)
    messages = await service.thread(session, conversation.id, staff=False, after=after)
    detail = ConversationDetail(**_summary(conversation).model_dump())
    detail.messages = await customer_messages(session, messages)
    return detail


@router.post(
    "/me/conversations/{conversation_id}/messages",
    response_model=ConversationDetail,
    status_code=201,
)
async def post_my_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ConversationDetail:
    """Write in a conversation (a resolved one reopens)."""
    user_id = current_user.id
    conversation = await _own(session, conversation_id, user_id)
    await _limit(f"msg-post:{user_id}", limit=60, window_seconds=600)
    await service.add_message(
        session,
        conversation,
        side=MessageSide.CUSTOMER,
        body=body.body,
        author_id=user_id,
    )
    await session.commit()
    return await _detail(session, conversation_id, user_id)


@router.post("/me/conversations/{conversation_id}/read", status_code=204)
async def read_my_conversation(
    conversation_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> None:
    conversation = await _own(session, conversation_id, current_user.id)
    service.mark_read(conversation, MessageSide.CUSTOMER, utcnow())
    session.add(conversation)
    await session.commit()


@router.post(
    "/me/conversations/{conversation_id}/resolve", response_model=ConversationSummary
)
async def resolve_my_conversation(
    conversation_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> ConversationSummary:
    """« My question is settled » (writing again reopens it)."""
    conversation = await _own(session, conversation_id, current_user.id)
    await service.resolve_by_customer(session, conversation, now=utcnow())
    await session.commit()
    await session.refresh(conversation)
    return _summary(conversation)


__all__ = ["router"]
