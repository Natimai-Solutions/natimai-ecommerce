"""
Tracking and event models.
Journal of all changes and step-by-step tracking.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import JSON, Column, Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class TrackingEventBase(Base):
    """Immutable journal of all changes for audit & timeline"""

    # Event subject (polymorphic)
    subject_type: str = Field(
        max_length=50, description="Entity type: route, step, consolidation, order_step"
    )
    subject_id: uuid.UUID = Field(description="ID of the concerned entity")

    # Status change
    status_from: str | None = Field(
        default=None, max_length=50, description="Previous status"
    )
    status_to: str = Field(max_length=50, description="New status")

    # Timing
    occurred_at: datetime = Field(description="When the event occurred")
    recorded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When it was recorded",
    )

    # Context
    scan_ref: str | None = Field(
        default=None, max_length=100, description="Scan/barcode reference"
    )
    location: str | None = Field(
        default=None, max_length=200, description="Event location"
    )
    actor: str | None = Field(
        default=None, max_length=100, description="Who triggered the event"
    )

    # Description
    event_type: str = Field(
        max_length=50, description="Event type: scan, update, exception"
    )
    description: str | None = Field(
        default=None, max_length=500, description="Free description"
    )

    # Flexible metadata
    event_metadata: str | None = Field(
        default=None, sa_column=Column(JSON), description="Additional data"
    )

    # Evidence
    evidence_url: str | None = Field(
        default=None, max_length=500, description="Evidence URL (photo, signature)"
    )
    signature_name: str | None = Field(
        default=None, max_length=100, description="Signatory name"
    )


class TrackingEventCreate(TrackingEventBase, BaseCreate):
    pass


class TrackingEventUpdate(BaseUpdate):
    # Tracking events should normally not be modified
    # Only description or metadata can be enriched
    description: str | None = None
    event_metadata: str | None = None
    evidence_url: str | None = None


class TrackingEvent(TrackingEventBase, table=True):
    """Immutable journal of all changes for audit & timeline"""

    __tablename__ = "tracking_events"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )


class TrackingEventPublic(TrackingEventBase, BasePublic):
    pass


class TrackingEventsPublic(SQLModel):
    data: list[TrackingEventPublic] = Field(
        default_factory=list,
        description="List of tracking events",
    )
    count: int = Field(
        default=0,
        description="Total number of tracking events",
    )
