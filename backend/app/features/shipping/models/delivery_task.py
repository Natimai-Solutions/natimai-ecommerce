"""
Simple delivery task models.
Final delivery management.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.place.models import Place


class DeliveryTaskBase(Base):
    """
    Simple final delivery task (home or pickup).
    """

    order_id: uuid.UUID = Field(description="Order ID to deliver")
    address_place_id: uuid.UUID = Field(
        foreign_key="places.id",
        description="Delivery place",
    )

    # Delivery type
    delivery_type: str = Field(
        max_length=50, description="Type: home_delivery, pickup_point"
    )

    # Assignment
    assignee: str | None = Field(
        default=None, max_length=100, description="Assigned delivery person"
    )

    # Status
    status_code: str | None = Field(
        default="pending", max_length=50, description="Task status"
    )

    scheduled_at: datetime | None = Field(
        default=None, description="Scheduled delivery date and time"
    )

    # Delivery completion
    delivered_at: datetime | None = Field(
        default=None, description="Delivery completed at"
    )

    # Notes
    notes: str | None = Field(
        default=None, max_length=500, description="Notes"
    )


class DeliveryTask(DeliveryTaskBase, table=True):
    """Simple final delivery task"""

    __tablename__ = "delivery_tasks"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    # Relations
    address_place: "Place" = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"}
    )


class DeliveryTaskCreate(DeliveryTaskBase, BaseCreate):
    pass


class DeliveryTaskUpdate(BaseUpdate):
    delivery_type: str | None = None
    assignee: str | None = None
    status_code: str | None = None
    delivered_at: datetime | None = None
    notes: str | None = None


class DeliveryTaskPublic(DeliveryTaskBase, BasePublic):
    id: uuid.UUID


class DeliveryTasksPublic(SQLModel):
    data: list[DeliveryTaskPublic] = Field(
        default_factory=list,
        description="List of delivery tasks",
    )
    count: int = Field(
        default=0,
        description="Total number of delivery tasks",
    )
