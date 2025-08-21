import uuid

from sqlmodel import Enum, Field, Relationship, SQLModel
from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic
from app.api.user.model import User


class AddressBase(Base):
    street: str = Field(description="Street address")
    city: str = Field(description="City of the address")
    state: str | None = Field(default=None, description="State of the address")
    postal_code: str = Field(description="Postal code of the address")
    country: str = Field(description="Country of the address")


class AddressCreate(AddressBase, BaseCreate):
    pass


class AddressUpdate(AddressBase, BaseUpdate):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


class Address(AddressBase, Base, table=True):
    __tablename__ = "addresses"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True, description="ID of the user"
    )


class AddressPublic(AddressBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class AddressesPublic(SQLModel):
    data: list[AddressPublic] = Field(
        default_factory=list, description="List of addresses"
    )
    count: int = Field(default=0, description="Total number of addresses")
