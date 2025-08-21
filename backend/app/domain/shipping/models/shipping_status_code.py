import uuid
from sqlmodel import Field, SQLModel

from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class ShippingStatusCodeBase(SQLModel):
    code: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="Stable code (e.g., PENDING, IN_TRANSIT, DELIVERED)",
    )
    label: str = Field(max_length=255, description="More readable label")
    description: str | None = Field(default=None, description="Optional description")
    sequence: int = Field(
        default=0,
        ge=0,
        description="Order of this status code in the flow",
        index=True,
    )


class ShippingStatusCodeCreate(ShippingStatusCodeBase, BaseCreate):
    pass


class ShippingStatusCodeUpdate(BaseUpdate):
    code: str | None = None
    label: str | None = None
    description: str | None = None


class ShippingStatusCode(ShippingStatusCodeBase, Base, table=True):
    __tablename__ = "shipping_status_code"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class ShippingStatusCodePublic(ShippingStatusCodeBase, BasePublic):
    id: uuid.UUID


class ShippingStatusCodesPublic(SQLModel):
    data: list[ShippingStatusCodePublic] = Field(default_factory=list)
    count: int = Field(default=0)