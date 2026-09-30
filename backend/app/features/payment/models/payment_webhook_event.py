# mypy: disable-error-code="assignment,misc,override"
"""Provider notifications already processed (R3-P4).

A provider delivers a notification at least once, often several times. The
generic webhook pipeline records the provider's event id here; a second
delivery of the same event is acknowledged without being applied twice.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class PaymentWebhookEvent(SQLModel, table=True):
    __tablename__ = "payment_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider_code", "event_id", name="uq_payment_webhook_event_provider"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    provider_code: str = Field(max_length=50)
    event_id: str = Field(max_length=255)
    event_type: str | None = Field(default=None, max_length=100)
    payment_id: uuid.UUID | None = Field(
        default=None, foreign_key="payments.id", nullable=True, index=True
    )
    #: What the pipeline did: applied, duplicate, conflict, amount_mismatch,
    #: ignored, unknown_payment.
    outcome: str = Field(max_length=30)
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
