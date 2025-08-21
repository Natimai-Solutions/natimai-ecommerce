import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class ShippingStatusBase(SQLModel):
    # Code de statut référencé
    status_code_id: uuid.UUID = Field(
        foreign_key="shipping_status_code.id",
        description="FK to shipping_status_code.id",
        index=True,
    )
    tracking_number: str | None = Field(
        default=None, description="Tracking number for the shipment", index=True
    )
    estimated_delivery_date: datetime | None = Field(
        default=None, description="Estimated delivery date for the shipment"
    )
    carrier: str | None = Field(default=None, description="Carrier handling the shipment")


class ShippingStatusCreate(ShippingStatusBase, BaseCreate):
    pass


class ShippingStatusUpdate(BaseUpdate):
    status_code_id: uuid.UUID | None = None
    sequence: int | None = None
    tracking_number: str | None = None
    estimated_delivery_date: datetime | None = None
    carrier: str | None = None


class ShippingStatus(ShippingStatusBase, Base, table=True):
    __tablename__ = "shipping_status"
    __table_args__ = (
        # Empêche deux statuts avec la même sequence pour un même tracking
        UniqueConstraint("tracking_number", "sequence", name="uq_shipping_status_track_seq"),
    )
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the shipping status",
    )


class ShippingStatusPublic(ShippingStatusBase, BasePublic):
    id: uuid.UUID


class ShippingStatusesPublic(SQLModel):
    data: list[ShippingStatusPublic] = Field(default_factory=list)
    count: int = Field(default=0)
