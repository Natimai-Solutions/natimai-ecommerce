"""Messaging, team side (chantier accueil et messagerie, lot MSG1).

The queue (tabs « to do », « mine », « waiting for the customer »,
« resolved », « all »), a conversation with its notes and events, and the
team's actions: answer or write a note, take, release, resolve, transfer,
move to another channel or topic. Paginated on the server.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep, module_required
from app.api.routes.messaging import (
    AttachmentPublic,
    ConversationSummary,
    _summary,
    attachments_of,
    file_response,
)
from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.features.messaging import attachments as files
from app.features.messaging import guests, service
from app.features.messaging.models import (
    BODY_MAX,
    CHANNELS,
    Conversation,
    ConversationAttachment,
    ConversationMessage,
    ConversationStatus,
    MessageKind,
    MessageSide,
)
from app.features.order.models.order import Order
from app.features.user.models.user import User

router = APIRouter(
    prefix="/admin/conversations",
    tags=["admin-messaging"],
    dependencies=[Depends(module_required("messaging"))],
)

Tab = Literal["todo", "mine", "pending", "resolved", "all"]


class StaffConversation(ConversationSummary):
    """A conversation as the team sees it."""

    customer_id: uuid.UUID | None = None
    customer_name: str = ""
    customer_email: str | None = None
    assigned_to_id: uuid.UUID | None = None
    assigned_to_name: str = ""
    #: A customer message the team has not read.
    staff_unread: bool = False
    resolved_at: datetime.datetime | None = None


class StaffMessage(BaseModel):
    id: uuid.UUID
    side: str
    kind: str
    body: str
    data: dict[str, object] = {}
    created_at: datetime.datetime
    author_name: str = ""
    attachments: list[AttachmentPublic] = []


class StaffConversationDetail(StaffConversation):
    messages: list[StaffMessage] = []
    #: Label of what the conversation refers to (order number…), if any.
    context_label: str | None = None


class ConversationPage(BaseModel):
    data: list[StaffConversation]
    count: int


class Summary(BaseModel):
    todo: int
    mine: int
    pending: int
    unread: int


class StaffMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=BODY_MAX)
    #: ``note``: internal, never shown to the customer.
    kind: Literal["message", "note"] = "message"


class TransferBody(BaseModel):
    user_id: uuid.UUID
    force: bool = False


class TopicBody(BaseModel):
    channel: str = Field(max_length=30)
    topic: str = Field(max_length=30)


class TeamMember(BaseModel):
    id: uuid.UUID
    name: str


async def _staff_view(
    session: SessionDep, conversation: Conversation
) -> StaffConversation:
    customer = (
        await session.get(User, conversation.customer_id)
        if conversation.customer_id
        else None
    )
    holder = (
        await session.get(User, conversation.assigned_to_id)
        if conversation.assigned_to_id
        else None
    )
    customer_at, read_at = (
        conversation.last_customer_message_at,
        conversation.staff_read_at,
    )
    return StaffConversation(
        **_summary(conversation).model_dump(),
        customer_id=conversation.customer_id,
        customer_name=service.display_name(customer)
        if customer
        else (conversation.guest_name or ""),
        customer_email=str(customer.email) if customer else conversation.guest_email,
        assigned_to_id=conversation.assigned_to_id,
        assigned_to_name=service.display_name(holder),
        staff_unread=bool(customer_at and (read_at is None or customer_at > read_at)),
        resolved_at=conversation.resolved_at,
    )


async def _get(session: SessionDep, conversation_id: uuid.UUID) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise service.not_found(conversation_id)
    return conversation


async def _context_label(session: SessionDep, conversation: Conversation) -> str | None:
    if conversation.context_type == "order" and conversation.context_id:
        order = await session.get(Order, conversation.context_id)
        return (order.order_number or str(order.id)[:8]) if order else None
    return None


@router.get("", response_model=ConversationPage)
async def list_conversations(
    session: SessionDep,
    admin: CurrentSuperUser,
    tab: Annotated[Tab, Query()] = "todo",
    channel: Annotated[str | None, Query(max_length=30)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ConversationPage:
    """The queue: « to do » (open and free), « mine », « waiting for the
    customer », « resolved », « all »; oldest waiting first in « to do »."""
    conditions: list[Any] = []
    status = col(Conversation.status)
    if tab == "todo":
        conditions += [
            status == ConversationStatus.OPEN.value,
            col(Conversation.assigned_to_id).is_(None),
        ]
    elif tab == "mine":
        conditions += [
            status != ConversationStatus.RESOLVED.value,
            col(Conversation.assigned_to_id) == admin.id,
        ]
    elif tab == "pending":
        conditions.append(status == ConversationStatus.PENDING.value)
    elif tab == "resolved":
        conditions.append(status == ConversationStatus.RESOLVED.value)
    if channel and channel in CHANNELS:
        conditions.append(col(Conversation.channel) == channel)
    if q and q.strip():
        escaped = (
            q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        customer_ids = select(User.id).where(
            or_(col(User.email).ilike(pattern), col(User.full_name).ilike(pattern))
        )
        order_ids = select(Order.id).where(col(Order.order_number).ilike(pattern))
        conditions.append(
            or_(
                col(Conversation.number).ilike(pattern),
                col(Conversation.subject).ilike(pattern),
                col(Conversation.guest_email).ilike(pattern),
                col(Conversation.guest_name).ilike(pattern),
                col(Conversation.customer_id).in_(customer_ids),
                col(Conversation.context_id).in_(order_ids),
            )
        )
    total = (
        await session.execute(
            select(func.count()).select_from(Conversation).where(*conditions)
        )
    ).scalar_one()
    order = (
        col(Conversation.last_message_at).asc()
        if tab == "todo"
        else col(Conversation.last_message_at).desc().nulls_last()
    )
    rows = await session.exec(
        select(Conversation)
        .where(*conditions)
        .order_by(order)
        .offset(skip)
        .limit(limit)
    )
    return ConversationPage(
        data=[await _staff_view(session, c) for c in rows.all()], count=int(total)
    )


@router.get("/summary", response_model=Summary)
async def conversations_summary(
    session: SessionDep, admin: CurrentSuperUser
) -> Summary:
    """Counters of the menu and the tabs."""
    summary = await service.staff_summary(session, admin.id)
    return Summary(
        todo=summary.todo,
        mine=summary.mine,
        pending=summary.pending,
        unread=summary.unread,
    )


@router.get("/team", response_model=list[TeamMember])
async def conversation_team(
    session: SessionDep, _admin: CurrentSuperUser
) -> list[TeamMember]:
    """Who a conversation can be transferred to."""
    rows = await session.exec(
        select(User).where(
            col(User.is_superuser).is_(True), col(User.is_active).is_(True)
        )
    )
    return [TeamMember(id=u.id, name=service.display_name(u)) for u in rows.all()]


@router.get("/{conversation_id}", response_model=StaffConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
    after: Annotated[datetime.datetime | None, Query()] = None,
) -> StaffConversationDetail:
    """A conversation with its messages, notes and events."""
    conversation = await _get(session, conversation_id)
    messages = await service.thread(session, conversation.id, staff=True, after=after)
    names: dict[uuid.UUID, str] = {}
    for author_id in {m.author_id for m in messages if m.author_id}:
        names[author_id] = service.display_name(await session.get(User, author_id))
    detail = StaffConversationDetail(
        **(await _staff_view(session, conversation)).model_dump()
    )
    detail.context_label = await _context_label(session, conversation)
    attached = await attachments_of(session, [m.id for m in messages])
    detail.messages = [
        StaffMessage(
            id=m.id,
            side=m.side,
            kind=m.kind,
            body=m.body,
            data=dict(m.data or {}),
            created_at=m.created_at,
            author_name=names.get(m.author_id, "") if m.author_id else "",
            attachments=attached.get(m.id, []),
        )
        for m in messages
    ]
    return detail


async def _email_guest(
    session: SessionDep, conversation_id: uuid.UUID, *, body: str, with_file: bool
) -> None:
    """A visitor without an account gets the reply by e-mail, with the link
    to continue on the site (lot MSG2)."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation is not None and conversation.customer_id is None:
        await guests.email_reply(session, conversation, body=body, with_file=with_file)


async def _detail(
    session: SessionDep, conversation_id: uuid.UUID, admin: User
) -> StaffConversationDetail:
    return await get_conversation(conversation_id, session, admin)


@router.post(
    "/{conversation_id}/messages",
    response_model=StaffConversationDetail,
    status_code=201,
)
async def post_staff_message(
    conversation_id: uuid.UUID,
    body: StaffMessageCreate,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> StaffConversationDetail:
    """Answer the customer, or write an internal note. The first answer takes
    a free conversation (never one someone else holds)."""
    conversation = await _get(session, conversation_id)
    now = utcnow()
    if body.kind == "message":
        await service.claim(session, conversation, admin, implicit=True, now=now)
    await service.add_message(
        session,
        conversation,
        side=MessageSide.STAFF,
        body=body.body,
        author_id=admin.id,
        kind=MessageKind(body.kind),
        now=now,
    )
    await session.commit()
    if body.kind == "message":
        await _email_guest(session, conversation_id, body=body.body, with_file=False)
    return await _detail(session, conversation_id, admin)


@router.post(
    "/{conversation_id}/attachments",
    response_model=StaffConversationDetail,
    status_code=201,
)
async def post_staff_file(
    conversation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentSuperUser,
    file: Annotated[UploadFile, File()],
    body: Annotated[str, Form(max_length=BODY_MAX)] = "",
    kind: Annotated[Literal["message", "note"], Form()] = "message",
) -> StaffConversationDetail:
    """Send a file to the customer (takes a free conversation), or join it to
    an internal note."""
    conversation = await _get(session, conversation_id)
    prepared = await files.prepare(await file.read(files.MAX_BYTES + 1))
    now = utcnow()
    if kind == "message":
        await service.claim(session, conversation, admin, implicit=True, now=now)
    message = await service.add_message(
        session,
        conversation,
        side=MessageSide.STAFF,
        body=body,
        author_id=admin.id,
        kind=MessageKind(kind),
        now=now,
        with_file=True,
    )
    await files.store(
        session,
        conversation,
        message_id=message.id,
        filename=file.filename,
        prepared=prepared,
        now=now,
    )
    await session.commit()
    if kind == "message":
        await _email_guest(session, conversation_id, body=body, with_file=True)
    return await _detail(session, conversation_id, admin)


@router.get("/{conversation_id}/attachments/{attachment_id}")
async def get_staff_file(
    conversation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> Response:
    attachment = await session.get(ConversationAttachment, attachment_id)
    if attachment is None or attachment.conversation_id != conversation_id:
        raise AppError(
            code="messaging.attachment.not_found",
            status_code=404,
            message="File not found.",
            details={},
        )
    return file_response(attachment, await files.read(attachment))


@router.post("/{conversation_id}/read", status_code=204)
async def read_conversation(
    conversation_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> None:
    conversation = await _get(session, conversation_id)
    service.mark_read(conversation, MessageSide.STAFF, utcnow())
    session.add(conversation)
    await session.commit()


@router.post("/{conversation_id}/claim", response_model=StaffConversationDetail)
async def claim_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentSuperUser,
    force: Annotated[bool, Query()] = False,
) -> StaffConversationDetail:
    """Take the conversation (409 if someone else holds it, unless ``force``)."""
    conversation = await _get(session, conversation_id)
    await service.claim(session, conversation, admin, force=force)
    await session.commit()
    return await _detail(session, conversation_id, admin)


@router.post("/{conversation_id}/release", response_model=StaffConversationDetail)
async def release_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentSuperUser,
    force: Annotated[bool, Query()] = False,
) -> StaffConversationDetail:
    conversation = await _get(session, conversation_id)
    await service.release(session, conversation, admin, force=force)
    await session.commit()
    return await _detail(session, conversation_id, admin)


@router.post("/{conversation_id}/resolve", response_model=StaffConversationDetail)
async def resolve_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentSuperUser,
    force: Annotated[bool, Query()] = False,
) -> StaffConversationDetail:
    conversation = await _get(session, conversation_id)
    await service.resolve_by_staff(session, conversation, admin, force=force)
    await session.commit()
    return await _detail(session, conversation_id, admin)


@router.post("/{conversation_id}/transfer", response_model=StaffConversationDetail)
async def transfer_conversation(
    conversation_id: uuid.UUID,
    body: TransferBody,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> StaffConversationDetail:
    conversation = await _get(session, conversation_id)
    await service.transfer(session, conversation, admin, body.user_id, force=body.force)
    await session.commit()
    return await _detail(session, conversation_id, admin)


@router.put("/{conversation_id}/topic", response_model=StaffConversationDetail)
async def move_conversation(
    conversation_id: uuid.UUID,
    body: TopicBody,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> StaffConversationDetail:
    """Move the conversation to another channel / topic (traced)."""
    conversation = await _get(session, conversation_id)
    await service.change_topic(
        session, conversation, admin, channel=body.channel, topic=body.topic
    )
    await session.commit()
    return await _detail(session, conversation_id, admin)


__all__ = ["ConversationMessage", "router"]
