# mypy: disable-error-code="assignment,misc,override"
"""Every e-mail the shop sends (« le client n'a rien reçu »).

One row per message, written by :mod:`app.features.notification.mailer`:
what was sent to whom, when, through which provider, and whether it went
out. The admin reads the journal and sends a message again. The body is kept
only while it may be resent: a message that carries a secret (password
reset link, sign-up code) is not resendable, and its body is dropped once
sent — the journal must not become a store of valid links.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel

STATUS_QUEUED = "queued"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"


class EmailLog(SQLModel, table=True):
    __tablename__ = "email_log"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    event_type: str = Field(max_length=100, index=True)
    recipient: str = Field(max_length=320, index=True)
    subject: str = Field(default="", max_length=500)
    body_text: str | None = Field(default=None, sa_column=Column(Text))
    body_html: str | None = Field(default=None, sa_column=Column(Text))
    #: queued, sent, failed.
    status: str = Field(default=STATUS_QUEUED, max_length=16, index=True)
    attempts: int = Field(default=0)
    last_error: str | None = Field(default=None, max_length=500)
    provider_code: str | None = Field(default=None, max_length=50)
    sent_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    resendable: bool = Field(default=True)
