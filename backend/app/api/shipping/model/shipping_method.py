import uuid

from sqlmodel import Field, SQLModel

from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class ShippingMethodBase(SQLModel):
    name: str = Field(..., description="Name of the shipping method")
    description: str = Field(None, description="Description of the shipping method")
    price: float = Field(..., description="Price of the shipping method")
    estimated_delivery_days: int = Field(
        ..., description="Estimated delivery days for the shipping method"
    )
    carrier: str = Field(
        None, description="Carrier associated with this shipping method"
    )


class ShippingMethodCreate(ShippingMethodBase, BaseCreate):
    pass


class ShippingMethodUpdate(ShippingMethodBase, BaseUpdate):
    pass


class ShippingMethod(ShippingMethodBase, Base, table=True):
    __tablename__ = "shipping_method"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the shipping method",
    )
    is_active: bool = Field(
        default=True, description="Indicates if the shipping method is active"
    )


class ShippingMethodPublic(ShippingMethodBase, BasePublic):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the shipping method",
    )


class ShippingMethodsPublic(SQLModel):
    data: list[ShippingMethodPublic] = Field(
        default_factory=list, description="List of shipping methods"
    )
