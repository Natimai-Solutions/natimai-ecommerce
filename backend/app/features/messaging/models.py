"""Messaging between a customer and the shop (chantier accueil et messagerie,
lot MSG1).

A **conversation** belongs to a channel (who answers) and a topic (what it is
about), chosen by the customer through the topic. Its messages are written by
the customer, by the team, or are internal notes and events the customer never
sees. Read and notification state is kept per side with timestamps (one
``UPDATE`` marks a conversation read).

Only ``kind = message`` moves the conversation: status, last-message times,
read and notified markers. A note or an event never does, so a note never
e-mails the customer.
"""

from __future__ import annotations

import datetime
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, Sequence, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.features.base.models import Base

#: Channels (who answers) and their topics (what it is about), in display
#: order. The customer picks a topic; the channel follows from it.
CHANNEL_TOPICS: dict[str, tuple[str, ...]] = {
    "customer_service": ("order_tracking", "delivery", "payment_invoice", "account"),
    "technical": ("setup_usage", "fault", "warranty_return"),
    "sales": ("pre_sale", "quote", "volume", "price_group"),
}
CHANNELS: tuple[str, ...] = tuple(CHANNEL_TOPICS)
TOPIC_CHANNEL: dict[str, str] = {
    topic: channel for channel, topics in CHANNEL_TOPICS.items() for topic in topics
}

#: What a conversation may be attached to.
CONTEXT_TYPES: tuple[str, ...] = ("order", "product", "quote_request", "group_request")

#: Number shown to the customer and on the phone (never a way in).
conversation_number_seq = Sequence(
    "conversation_number_seq", metadata=SQLModel.metadata
)

BODY_MAX = 4000
SUBJECT_MAX = 200


class ConversationStatus(StrEnum):
    """``open``: the team has to answer; ``pending``: waiting for the
    customer; ``resolved``: settled (a customer message reopens it)."""

    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"


class MessageSide(StrEnum):
    CUSTOMER = "customer"
    STAFF = "staff"


class MessageKind(StrEnum):
    """``note``: internal, team only. ``event``: a trace of the team's work
    (taken, transferred…), team only."""

    MESSAGE = "message"
    NOTE = "note"
    EVENT = "event"


class Conversation(Base, table=True):
    """A conversation between a customer (or a visitor) and the shop."""

    __tablename__ = "conversations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    number: str = Field(max_length=20, unique=True, index=True)
    channel: str = Field(max_length=30, index=True)
    topic: str = Field(max_length=30)
    status: str = Field(
        default=ConversationStatus.OPEN.value, max_length=20, index=True
    )
    subject: str = Field(max_length=SUBJECT_MAX)
    customer_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", index=True, ondelete="CASCADE"
    )
    #: A visitor without an account (public contact form, lot MSG2).
    guest_name: str | None = Field(default=None, max_length=255)
    guest_email: str | None = Field(default=None, max_length=255, index=True)
    guest_phone: str | None = Field(default=None, max_length=50)
    guest_company: str | None = Field(default=None, max_length=255)
    guest_locale: str | None = Field(default=None, max_length=10)
    context_type: str | None = Field(default=None, max_length=30)
    context_id: uuid.UUID | None = Field(default=None, index=True)
    assigned_to_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", index=True, ondelete="SET NULL"
    )
    assigned_at: datetime.datetime | None = None
    last_message_at: datetime.datetime | None = Field(default=None, index=True)
    last_customer_message_at: datetime.datetime | None = None
    last_staff_message_at: datetime.datetime | None = None
    customer_read_at: datetime.datetime | None = None
    #: Shared by the whole team (a conversation read by one is read by all).
    staff_read_at: datetime.datetime | None = None
    customer_notified_at: datetime.datetime | None = None
    staff_notified_at: datetime.datetime | None = None
    #: First answer of the team (response-time statistics).
    first_staff_reply_at: datetime.datetime | None = None
    resolved_at: datetime.datetime | None = None
    #: Kept longer at the customer's request (« keep one more year »).
    retain_until: datetime.datetime | None = None
    deletion_notice_at: datetime.datetime | None = None


class ConversationMessage(SQLModel, table=True):
    """A message, an internal note or an event of a conversation."""

    __tablename__ = "conversation_messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="conversations.id", index=True, ondelete="CASCADE"
    )
    #: None for a visitor without an account.
    author_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", ondelete="SET NULL"
    )
    side: str = Field(max_length=20)
    kind: str = Field(default=MessageKind.MESSAGE.value, max_length=20)
    body: str = Field(sa_column=Column(Text, nullable=False))
    #: Event parameters (who took it, to whom it was transferred…).
    data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    created_at: datetime.datetime = Field(index=True)


class ConversationAttachment(SQLModel, table=True):
    """A file joined to a message. Only clean files are stored (scanned at
    upload); images are re-encoded without their metadata."""

    __tablename__ = "conversation_attachments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="conversations.id", index=True, ondelete="CASCADE"
    )
    message_id: uuid.UUID = Field(
        foreign_key="conversation_messages.id", index=True, ondelete="CASCADE"
    )
    #: Name shown to the reader (sanitised); never part of the storage key.
    filename: str = Field(max_length=255)
    mime: str = Field(max_length=100)
    size: int
    sha256: str = Field(max_length=64)
    object_key: str = Field(max_length=500)
    created_at: datetime.datetime


__all__ = [
    "BODY_MAX",
    "CHANNELS",
    "CHANNEL_TOPICS",
    "CONTEXT_TYPES",
    "SUBJECT_MAX",
    "TOPIC_CHANNEL",
    "Conversation",
    "ConversationAttachment",
    "ConversationMessage",
    "ConversationStatus",
    "MessageKind",
    "MessageSide",
    "conversation_number_seq",
]
