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

from app.api.deps import (
    CurrentMessagingStaff,
    CurrentSuperUser,
    SessionDep,
    module_required,
)
from app.api.routes.messaging import (
    AttachmentPublic,
    ConversationSummary,
    _summary,
    attachments_of,
    file_response,
)
from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.core.i18n import offered_locales
from app.features.cart.models.quote_request import QuoteRequest
from app.features.messaging import attachments as files
from app.features.messaging import guests, service
from app.features.messaging.models import (
    BODY_MAX,
    CHANNELS,
    CannedReply,
    Conversation,
    ConversationAttachment,
    ConversationMessage,
    ConversationStatus,
    MessageKind,
    MessageSide,
)
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.services import loyalty
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import Product
from app.features.product.services.group_pricing import resolve_customer_group
from app.features.product.services.pricing import resolve_default_price_group
from app.features.user.crud.user_preference import get_preference_for_user
from app.features.user.models.group_upgrade_request import GroupUpgradeRequest
from app.features.user.models.user import User
from app.features.user.staff import STAFF_ROLES, staff_channels

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
    #: The customer's price group comes first in the queue (MSG4).
    priority: bool = False
    #: Language of the customer (the canned replies follow it).
    customer_locale: str | None = None
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


class PanelOrder(BaseModel):
    id: uuid.UUID
    number: str | None = None
    status: str | None = None
    total_amount: str | None = None
    currency: str | None = None
    created_at: datetime.datetime | None = None


class CustomerPanel(BaseModel):
    """The customer beside the thread (lot MSG3): their price group, last
    orders and loyalty points — what an answer usually needs."""

    price_group_label: str | None = None
    orders: list[PanelOrder] = []
    loyalty_points: int | None = None
    phone: str | None = None


class StaffConversationDetail(StaffConversation):
    messages: list[StaffMessage] = []
    customer_panel: CustomerPanel | None = None
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
    group = await resolve_customer_group(session, customer) if customer else None
    preference = (
        await get_preference_for_user(session, user_id=customer.id)
        if customer
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
        priority=bool(group and group.messaging_priority),
        customer_locale=(preference.locale if preference else None)
        or conversation.guest_locale,
    )


async def _get(
    session: SessionDep, conversation_id: uuid.UUID, channels: tuple[str, ...]
) -> Conversation:
    """A conversation of the channels the team member works on; any other
    reads as missing (lot ROLE). ``channels`` is read from the user before
    any commit: a commit expires the signed-in user of the request."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.channel not in channels:
        raise service.not_found(conversation_id)
    return conversation


async def _customer_panel(session: SessionDep, customer_id: uuid.UUID) -> CustomerPanel:
    customer = await session.get(User, customer_id)
    group = await resolve_customer_group(session, customer) if customer else None
    rows = (
        await session.exec(
            select(Order, OrderStatus.name)
            .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
            .where(col(Order.user_id) == customer_id)
            .order_by(col(Order.created_at).desc())
            .limit(5)
        )
    ).all()
    try:
        points: int | None = await loyalty.balance(session, customer_id)
    except Exception:  # noqa: BLE001 - the panel never breaks the thread
        points = None
    return CustomerPanel(
        price_group_label=group.label if group else None,
        orders=[
            PanelOrder(
                id=order.id,
                number=order.order_number,
                status=status_name,
                total_amount=str(order.total_amount),
                currency=order.currency,
                created_at=order.created_at,
            )
            for order, status_name in rows
        ],
        loyalty_points=points,
        phone=customer.phone if customer else None,
    )


async def _context_label(session: SessionDep, conversation: Conversation) -> str | None:
    """What the conversation refers to, as the team reads it."""
    if not conversation.context_id:
        return None
    if conversation.context_type == "order":
        order = await session.get(Order, conversation.context_id)
        return (order.order_number or str(order.id)[:8]) if order else None
    if conversation.context_type == "quote_request":
        quote = await session.get(QuoteRequest, conversation.context_id)
        return (quote.quote_number or quote.email) if quote else None
    if conversation.context_type == "product":
        product = await session.get(Product, conversation.context_id)
        return product.name if product else None
    if conversation.context_type == "group_request":
        request = await session.get(GroupUpgradeRequest, conversation.context_id)
        group = (
            await session.get(PriceGroup, request.price_group_id) if request else None
        )
        return group.label if group else None
    return None


@router.get("", response_model=ConversationPage)
async def list_conversations(
    session: SessionDep,
    admin: CurrentMessagingStaff,
    tab: Annotated[Tab, Query()] = "todo",
    channel: Annotated[str | None, Query(max_length=30)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ConversationPage:
    """The queue: « to do » (open and free), « mine », « waiting for the
    customer », « resolved », « all »; oldest waiting first in « to do »."""
    # Each team member sees the channels of their role (lot ROLE).
    conditions: list[Any] = [col(Conversation.channel).in_(staff_channels(admin))]
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
    # « To do »: the priority groups' customers first, then the oldest.
    default_group = await resolve_default_price_group(session)
    priority = func.coalesce(
        col(PriceGroup.messaging_priority),
        bool(default_group and default_group.messaging_priority),
    )
    order = (
        [priority.desc(), col(Conversation.last_message_at).asc()]
        if tab == "todo"
        else [col(Conversation.last_message_at).desc().nulls_last()]
    )
    rows = await session.exec(
        select(Conversation)
        .outerjoin(User, col(User.id) == col(Conversation.customer_id))
        .outerjoin(PriceGroup, col(PriceGroup.id) == col(User.price_group_id))
        .where(*conditions)
        .order_by(*order)
        .offset(skip)
        .limit(limit)
    )
    return ConversationPage(
        data=[await _staff_view(session, c) for c in rows.all()], count=int(total)
    )


@router.get("/summary", response_model=Summary)
async def conversations_summary(
    session: SessionDep, admin: CurrentMessagingStaff
) -> Summary:
    """Counters of the menu and the tabs."""
    summary = await service.staff_summary(
        session, admin.id, channels=staff_channels(admin)
    )
    return Summary(
        todo=summary.todo,
        mine=summary.mine,
        pending=summary.pending,
        unread=summary.unread,
    )


@router.get("/team", response_model=list[TeamMember])
async def conversation_team(
    session: SessionDep,
    _admin: CurrentMessagingStaff,
    channel: Annotated[str | None, Query(max_length=30)] = None,
) -> list[TeamMember]:
    """Who a conversation (of ``channel``) can be transferred to: the
    superusers and the team members whose role covers the channel."""
    rows = await session.exec(
        select(User).where(
            or_(
                col(User.is_superuser).is_(True),
                col(User.staff_role).in_(list(STAFF_ROLES)),
            ),
            col(User.is_active).is_(True),
        )
    )
    return [
        TeamMember(id=u.id, name=service.display_name(u))
        for u in rows.all()
        if channel is None or channel in staff_channels(u)
    ]


@router.get("/{conversation_id}", response_model=StaffConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentMessagingStaff,
    after: Annotated[datetime.datetime | None, Query()] = None,
) -> StaffConversationDetail:
    """A conversation with its messages, notes and events."""
    return await _detail(session, conversation_id, staff_channels(_admin), after=after)


async def _email_guest(
    session: SessionDep, conversation_id: uuid.UUID, *, body: str, with_file: bool
) -> None:
    """A visitor without an account gets the reply by e-mail, with the link
    to continue on the site (lot MSG2)."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation is not None and conversation.customer_id is None:
        await guests.email_reply(session, conversation, body=body, with_file=with_file)


async def _detail(
    session: SessionDep,
    conversation_id: uuid.UUID,
    channels: tuple[str, ...],
    *,
    after: datetime.datetime | None = None,
) -> StaffConversationDetail:
    conversation = await _get(session, conversation_id, channels)
    messages = await service.thread(session, conversation.id, staff=True, after=after)
    names: dict[uuid.UUID, str] = {}
    for author_id in {m.author_id for m in messages if m.author_id}:
        names[author_id] = service.display_name(await session.get(User, author_id))
    detail = StaffConversationDetail(
        **(await _staff_view(session, conversation)).model_dump()
    )
    detail.context_label = await _context_label(session, conversation)
    if conversation.customer_id is not None:
        detail.customer_panel = await _customer_panel(session, conversation.customer_id)
    elif conversation.guest_phone:
        detail.customer_panel = CustomerPanel(phone=conversation.guest_phone)
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


@router.post(
    "/{conversation_id}/messages",
    response_model=StaffConversationDetail,
    status_code=201,
)
async def post_staff_message(
    conversation_id: uuid.UUID,
    body: StaffMessageCreate,
    session: SessionDep,
    admin: CurrentMessagingStaff,
) -> StaffConversationDetail:
    """Answer the customer, or write an internal note. The first answer takes
    a free conversation (never one someone else holds)."""
    channels = staff_channels(admin)
    conversation = await _get(session, conversation_id, channels)
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
    return await _detail(session, conversation_id, channels)


@router.post(
    "/{conversation_id}/attachments",
    response_model=StaffConversationDetail,
    status_code=201,
)
async def post_staff_file(
    conversation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentMessagingStaff,
    file: Annotated[UploadFile, File()],
    body: Annotated[str, Form(max_length=BODY_MAX)] = "",
    kind: Annotated[Literal["message", "note"], Form()] = "message",
) -> StaffConversationDetail:
    """Send a file to the customer (takes a free conversation), or join it to
    an internal note."""
    channels = staff_channels(admin)
    conversation = await _get(session, conversation_id, channels)
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
    return await _detail(session, conversation_id, channels)


@router.get("/{conversation_id}/attachments/{attachment_id}")
async def get_staff_file(
    conversation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentMessagingStaff,
) -> Response:
    await _get(session, conversation_id, staff_channels(_admin))
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
    conversation_id: uuid.UUID, session: SessionDep, admin: CurrentMessagingStaff
) -> None:
    channels = staff_channels(admin)
    conversation = await _get(session, conversation_id, channels)
    service.mark_read(conversation, MessageSide.STAFF, utcnow())
    session.add(conversation)
    await session.commit()


@router.post("/{conversation_id}/claim", response_model=StaffConversationDetail)
async def claim_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentMessagingStaff,
    force: Annotated[bool, Query()] = False,
) -> StaffConversationDetail:
    """Take the conversation (409 if someone else holds it, unless ``force``)."""
    channels = staff_channels(admin)
    conversation = await _get(session, conversation_id, channels)
    await service.claim(session, conversation, admin, force=force)
    await session.commit()
    return await _detail(session, conversation_id, channels)


@router.post("/{conversation_id}/release", response_model=StaffConversationDetail)
async def release_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentMessagingStaff,
    force: Annotated[bool, Query()] = False,
) -> StaffConversationDetail:
    channels = staff_channels(admin)
    conversation = await _get(session, conversation_id, channels)
    await service.release(session, conversation, admin, force=force)
    await session.commit()
    return await _detail(session, conversation_id, channels)


@router.post("/{conversation_id}/resolve", response_model=StaffConversationDetail)
async def resolve_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentMessagingStaff,
    force: Annotated[bool, Query()] = False,
) -> StaffConversationDetail:
    channels = staff_channels(admin)
    conversation = await _get(session, conversation_id, channels)
    await service.resolve_by_staff(session, conversation, admin, force=force)
    await session.commit()
    return await _detail(session, conversation_id, channels)


@router.post("/{conversation_id}/transfer", response_model=StaffConversationDetail)
async def transfer_conversation(
    conversation_id: uuid.UUID,
    body: TransferBody,
    session: SessionDep,
    admin: CurrentMessagingStaff,
) -> StaffConversationDetail:
    channels = staff_channels(admin)
    conversation = await _get(session, conversation_id, channels)
    await service.transfer(session, conversation, admin, body.user_id, force=body.force)
    await session.commit()
    return await _detail(session, conversation_id, channels)


@router.put("/{conversation_id}/topic", response_model=StaffConversationDetail)
async def move_conversation(
    conversation_id: uuid.UUID,
    body: TopicBody,
    session: SessionDep,
    admin: CurrentMessagingStaff,
) -> StaffConversationDetail:
    """Move the conversation to another channel / topic (traced)."""
    channels = staff_channels(admin)
    conversation = await _get(session, conversation_id, channels)
    await service.change_topic(
        session, conversation, admin, channel=body.channel, topic=body.topic
    )
    await session.commit()
    return await _detail(session, conversation_id, channels)


# --- Canned replies (MSG4) ---------------------------------------------------
canned_router = APIRouter(
    prefix="/admin/canned-replies",
    tags=["admin-messaging"],
    dependencies=[Depends(module_required("messaging"))],
)


class CannedReplyWrite(BaseModel):
    channel: str | None = Field(default=None, max_length=30)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=BODY_MAX)
    #: ``{"en": {"title": …, "body": …}}``
    translations: dict[str, dict[str, str]] = Field(default_factory=dict)


class CannedReplyPublic(CannedReplyWrite):
    id: uuid.UUID
    position: int


def _clean_canned(body: CannedReplyWrite) -> CannedReplyWrite:
    if body.channel is not None and body.channel not in CHANNELS:
        raise AppError(
            code="messaging.topic",
            status_code=400,
            message="Unknown topic: {topic}.",
            details={"field": "channel", "topic": body.channel},
        )
    translations = {
        lang: {
            k: str(v).strip()[: 120 if k == "title" else BODY_MAX]
            for k, v in texts.items()
            if k in ("title", "body") and str(v).strip()
        }
        for lang, texts in body.translations.items()
        if lang in offered_locales()
    }
    return body.model_copy(
        update={"translations": {k: v for k, v in translations.items() if v}}
    )


@canned_router.get("", response_model=list[CannedReplyPublic])
async def list_canned_replies(
    session: SessionDep, admin: CurrentMessagingStaff
) -> list[CannedReplyPublic]:
    """The prepared answers of the channels the member works on."""
    channels = staff_channels(admin)
    rows = await session.exec(
        select(CannedReply)
        .where(
            or_(
                col(CannedReply.channel).is_(None),
                col(CannedReply.channel).in_(channels),
            )
        )
        .order_by(col(CannedReply.position), col(CannedReply.title))
    )
    return [
        CannedReplyPublic.model_validate(r, from_attributes=True) for r in rows.all()
    ]


@canned_router.post("", response_model=CannedReplyPublic, status_code=201)
async def create_canned_reply(
    body: CannedReplyWrite, session: SessionDep, admin: CurrentSuperUser
) -> CannedReplyPublic:
    clean = _clean_canned(body)
    last = (
        await session.exec(
            select(func.max(CannedReply.position)).select_from(CannedReply)
        )
    ).first()
    row = CannedReply(
        **clean.model_dump(),
        position=(last or 0) + 1,
        created_at=utcnow(),
        created_by_id=admin.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return CannedReplyPublic.model_validate(row, from_attributes=True)


async def _canned(session: SessionDep, reply_id: uuid.UUID) -> CannedReply:
    row = await session.get(CannedReply, reply_id)
    if row is None:
        raise AppError(
            code="messaging.canned_not_found",
            status_code=404,
            message="Prepared answer not found.",
            details={},
        )
    return row


@canned_router.put("/{reply_id}", response_model=CannedReplyPublic)
async def replace_canned_reply(
    reply_id: uuid.UUID,
    body: CannedReplyWrite,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> CannedReplyPublic:
    row = await _canned(session, reply_id)
    for key, value in _clean_canned(body).model_dump().items():
        setattr(row, key, value)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return CannedReplyPublic.model_validate(row, from_attributes=True)


@canned_router.delete("/{reply_id}", status_code=204)
async def delete_canned_reply(
    reply_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> None:
    await session.delete(await _canned(session, reply_id))
    await session.commit()


__all__ = ["ConversationMessage", "canned_router", "router"]
