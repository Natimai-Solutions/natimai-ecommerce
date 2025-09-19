import uuid
from typing import Annotated

from pydantic import Field as PydanticField, field_validator
from sqlmodel import Field, Relationship, SQLModel
from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic
from .user import User


def validate_address_type(v: str) -> str:
    """Validate that address type is one of the allowed values."""
    allowed_types = {"billing", "shipping", "other"}
    if v not in allowed_types:
        raise ValueError(f"Type must be one of: {', '.join(allowed_types)}")
    return v


class AddressBase(Base):
    street: str = Field(description="Street address")
    city: str = Field(description="City of the address")
    state: str | None = Field(default=None, description="State of the address")
    postal_code: str = Field(description="Postal code of the address")
    country: str = Field(description="Country of the address")
    type: str = Field(description="Address type: billing, shipping, or other")

    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate that type is one of the allowed values."""
        return validate_address_type(v)


class AddressCreate(AddressBase, BaseCreate):
    pass


class AddressUpdate(AddressBase, BaseUpdate):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    type: str | None = None


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
