import uuid

from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic
from sqlmodel import Field, SQLModel


class ShippingZoneBase(Base):
    name: str = Field(..., description="Name of the shipping zone")
    description: str = Field(None, description="Description of the shipping zone")
    region: str = Field(..., description="Region covered by this shipping zone")
    max_weight: float = Field(
        None, description="Maximum weight allowed for shipments in this zone"
    )
    is_active: bool = Field(
        default=True, description="Indicates if the shipping zone is active"
    )


class ShippingZoneCreate(ShippingZoneBase, BaseCreate):
    pass


class ShippingZoneUpdate(ShippingZoneBase, BaseUpdate):
    pass


class ShippingZone(ShippingZoneBase, Base, table=True):
    __tablename__ = "shipping_zone"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the shipping zone",
    )


class ShippingZonePublic(ShippingZoneBase, BasePublic):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the shipping zone",
    )


class ShippingZonesPublic(SQLModel):
    data: list[ShippingZonePublic] = Field(
        default_factory=list, description="List of shipping zones"
    )
