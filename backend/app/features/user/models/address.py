import uuid

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


def validate_address_type(v: str, field_name: str = "Address type") -> str:
    """Validate address type field."""
    allowed_types = {"billing", "shipping", "other"}
    if v not in allowed_types:
        raise ValueError(f"{field_name} must be one of: {', '.join(allowed_types)}")
    return v


class AddressBase(Base):
    street: str = Field(description="Street address")
    city: str = Field(description="City of the address")
    state: str | None = Field(default=None, description="State of the address")
    postal_code: str = Field(description="Postal code of the address")
    country: str = Field(description="Country of the address")
    type: str = Field(
        index=True,
        description="Address type: billing, shipping, or other",
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        return validate_address_type(v)


class AddressCreate(AddressBase, BaseCreate):
    user_id: uuid.UUID = Field(description="ID of the user")


class AddressUpdate(AddressBase, BaseUpdate):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    type: str | None = None
    user_id: uuid.UUID | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_address_type(v)
        return v


class Address(AddressBase, table=True):
    __tablename__ = "addresses"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True, description="ID of the user"
    )


class AddressPublic(AddressBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(description="ID of the user")


class AddressesPublic(SQLModel):
    data: list[AddressPublic] = Field(
        default_factory=list, description="List of addresses"
    )
    count: int = Field(default=0, description="Total number of addresses")
