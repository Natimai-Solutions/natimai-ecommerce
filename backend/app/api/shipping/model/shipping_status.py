import uuid

from sqlmodel import Field, SQLModel
from datetime import datetime

from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class ShippingStatusBase(Base):
    status: str = Field(..., description="Current status of the shipping")
    tracking_number: str = Field(None, description="Tracking number for the shipment")
    estimated_delivery_date: datetime | None = Field(
        None, description="Estimated delivery date for the shipment"
    )
    carrier: str = Field(None, description="Carrier handling the shipment")
    last_updated: datetime | None = Field(
        default_factory=datetime.now, description="Last updated timestamp"
    )


class ShippingStatusCreate(ShippingStatusBase, BaseCreate):
    pass


class ShippingStatusUpdate(BaseUpdate, ShippingStatusBase):
    pass


class ShippingStatus(ShippingStatusBase, Base, table=True):
    __tablename__ = "shipping_status"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the shipping status",
    )
    is_active: bool = Field(
        default=True, description="Indicates if the shipping status is active"
    )


class ShippingStatusPublic(ShippingStatusBase, BasePublic):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the shipping status",
    )
    is_active: bool = Field(
        default=True, description="Indicates if the shipping status is active"
    )


class ShippingStatusesPublic(SQLModel):
    data: list[ShippingStatusPublic] = Field(
        default_factory=list, description="List of shipping statuses"
    )
